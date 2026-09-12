"""Sketchboard Discord bot: sketch in, mockup out, the thread is the session.

Ways in:
  * Post an image in a channel the bot can see (message text = notes)
        -> the bot opens a thread on that message and posts the mockup there
  * /sketch image:<attachment> notes:<text>
        -> the bot posts your sketch in the channel, opens a thread, posts the mockup there
  * Reply inside a mockup thread ("make the button green")
        -> edited mockup in the thread

Runs on the GPU box next to the harness and talks to it on localhost. The Discord
gateway is an outbound websocket, so no inbound port, no TLS, no public URL.
Setup: discordbot/README.md.
"""

import io
import json
import logging
import os
import re
import time
from typing import Any

import discord
import httpx
from discord import app_commands

log = logging.getLogger("sketchboard.discord")

HARNESS = os.environ.get("HARNESS_URL", "http://127.0.0.1:8000").rstrip("/")
REQUIRE_MENTION = os.environ.get("DISCORD_REQUIRE_MENTION", "0") == "1"
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "2"))
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}

intents = discord.Intents.default()
intents.message_content = True   # privileged: enable it in the developer portal too
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
http = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=10))


# --- helpers ------------------------------------------------------------------------

def session_id(thread_id: int) -> str:
    """Deterministic id from the thread. A thread opened on a message shares its id."""
    return f"discord-{thread_id}"


def strip_mentions(text: str) -> str:
    return re.sub(r"<@!?\d+>", "", text or "").strip()


def is_image(a: discord.Attachment) -> bool:
    return (a.content_type or "").split(";")[0].lower() in IMAGE_MIMES


def thread_name(notes: str) -> str:
    base = (notes or "Mockup").strip().splitlines()[0]
    return (base[:60] + "…") if len(base) > 60 else base


def quote(text: str, limit: int = 600) -> str:
    text = text.strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return "\n".join("> " + l for l in text.splitlines())


async def download(a: discord.Attachment) -> tuple[bytes, str]:
    mime = (a.content_type or "").split(";")[0].lower()
    if mime not in IMAGE_MIMES:
        raise ValueError(f"unsupported image type {mime or 'unknown'}; use a JPEG or PNG")
    return await a.read(), mime


async def harness_stream(path: str, body: dict[str, Any]):
    async with http.stream("POST", f"{HARNESS}{path}", json=body) as r:
        if r.status_code != 200:
            await r.aread()
            raise RuntimeError(f"harness {r.status_code}: {r.text[:200]}")
        async for line in r.aiter_lines():
            if line.strip():
                yield json.loads(line)


async def session_exists(sid: str) -> bool:
    r = await http.get(f"{HARNESS}/api/v1/session/{sid}", timeout=10)
    return r.status_code == 200 and bool(r.json().get("html"))


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode()


# --- the two jobs ---------------------------------------------------------------------

async def run_mockup(thread: discord.Thread, sketch: bytes, mime: str, notes: str) -> None:
    sid = session_id(thread.id)
    status = await thread.send("Drafting a mockup from your sketch…")
    t0 = time.time()
    final = None
    try:
        body = {"image_base64": _b64(sketch), "mime": mime, "description": notes, "session_id": sid,
                "stream": False, "max_iterations": MAX_ITERATIONS}
        async for ev in harness_stream("/api/v1/mockup", body):
            t = ev["type"]
            if t == "draft":
                await status.edit(content=f"Draft {ev['iteration']} ready in {ev['seconds']} s. Checking it against the sketch…")
            elif t == "verdict":
                await status.edit(content="The judge wants changes, revising…\n" + quote(ev.get("problems", "")))
            elif t == "approved":
                await status.edit(content="Approved by the judge. Rendering…")
            elif t == "final":
                final = ev
            elif t == "error":
                raise RuntimeError(ev.get("message", "unknown error"))
    except Exception as e:  # noqa: BLE001
        log.exception("mockup failed")
        await status.edit(content=f"⚠️ Couldn't make a mockup: {e}")
        return
    if final is None:
        await status.edit(content="⚠️ The harness ended without a result.")
        return
    await post_result(thread, sid, status, final, time.time() - t0, "Mockup")


async def run_edit(thread: discord.Thread, instruction: str) -> None:
    sid = session_id(thread.id)
    status = await thread.send(f"Applying “{instruction}”…")
    t0 = time.time()
    final = None
    try:
        async for ev in harness_stream("/api/v1/edit", {"session_id": sid, "instruction": instruction, "stream": False}):
            t = ev["type"]
            if t == "patch":
                await status.edit(content=f"Patched {ev.get('hunks', '?')} place(s) in {ev.get('seconds', '?')} s. Rendering…")
            elif t == "final":
                final = ev
            elif t == "error":
                raise RuntimeError(ev.get("message", "unknown error"))
    except Exception as e:  # noqa: BLE001
        log.exception("edit failed")
        await status.edit(content=f"⚠️ Couldn't apply that: {e}")
        return
    if final is None:
        await status.edit(content="⚠️ The harness ended without a result.")
        return
    await post_result(thread, sid, status, final, time.time() - t0, "Updated mockup")


async def post_result(thread: discord.Thread, sid: str, status: discord.Message, final, elapsed, verb) -> None:
    png = (await http.get(f"{HARNESS}/api/v1/session/{sid}/render.png", timeout=60)).content
    info = (await http.get(f"{HARNESS}/api/v1/session/{sid}", timeout=10)).json()
    link = info.get("viewer_url")
    how = "approved by the judge" if final.get("approved") else f"best of {int(final.get('iterations', 0)) + 1} drafts"
    lines = [f"**{verb}** ready in {elapsed:.0f} s, {how}."]
    if link:
        lines.append(f"[Open the live mockup](<{link}>)")
    lines.append("Reply in this thread to change it, e.g. *make the button green*.")
    await thread.send("\n".join(lines), file=discord.File(io.BytesIO(png), filename="mockup.png"))
    try:
        await status.delete()
    except discord.HTTPException:
        pass


# --- Discord entry points ------------------------------------------------------------------

@client.event
async def on_ready():
    # Global sync can take up to an hour to show up; a per-guild sync is immediate.
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    await tree.sync()
    log.info("logged in as %s, harness %s, require_mention=%s, servers=%s",
             client.user, HARNESS, REQUIRE_MENTION, [g.name for g in client.guilds] or "none yet")


@client.event
async def on_guild_join(guild: discord.Guild):
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    log.info("added to server %s; /sketch synced", guild.name)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    images = [a for a in message.attachments if is_image(a)]
    text = strip_mentions(message.content)
    mentioned = client.user is not None and client.user in message.mentions
    channel = message.channel

    if isinstance(channel, discord.Thread):
        # Inside a thread: a text reply edits the mockup, if this thread has one.
        if text and not images and await session_exists(session_id(channel.id)):
            await run_edit(channel, text)
        elif mentioned and not images:
            await channel.send("No mockup in this thread yet. Post a sketch image in the channel, or use `/sketch`.")
        return

    if images and isinstance(channel, discord.TextChannel):
        if REQUIRE_MENTION and not mentioned:
            return
        try:
            sketch, mime = await download(images[0])
        except ValueError as e:
            await message.reply(f"⚠️ {e}")
            return
        thread = await message.create_thread(name=thread_name(text))
        await run_mockup(thread, sketch, mime, text)
    elif mentioned and not images:
        await message.reply("Post a sketch as an image (a whiteboard photo works) with a line of notes, or type `/sketch`. "
                            "I'll open a thread with the mockup; reply there to change it.")


@tree.command(name="sketch", description="Turn a sketch into a UI mockup")
@app_commands.describe(image="Photo or drawing of the screen (JPEG/PNG)", notes="What the screen is, in a sentence")
async def sketch(interaction: discord.Interaction, image: discord.Attachment, notes: str = ""):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("Run `/sketch` in a regular text channel, not a thread or DM.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        sketch_bytes, mime = await download(image)
    except ValueError as e:
        await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
        return
    root = await interaction.channel.send(
        f"{interaction.user.mention} asked for a mockup" + (f": *{notes}*" if notes else ""),
        file=discord.File(io.BytesIO(sketch_bytes), filename="sketch." + ("png" if mime == "image/png" else "jpg")),
    )
    thread = await root.create_thread(name=thread_name(notes))
    await interaction.followup.send(f"Working on it in {thread.mention}.", ephemeral=True)
    await run_mockup(thread, sketch_bytes, mime, notes)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is not set")
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
