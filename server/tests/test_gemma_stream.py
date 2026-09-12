"""chat_stream parses Ollama's OpenAI-style SSE and fills in the Reply."""

import asyncio
import json

import httpx

from app.gemma import Gemma


def _sse(chunks):
    lines = []
    for c in chunks:
        lines.append("data: " + json.dumps(c) + "\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def test_chat_stream_deltas_and_usage():
    seen_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_body.update(json.loads(request.content))
        body = _sse([
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
        ])
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    g = Gemma(base_url="http://fake")
    g._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def go():
        reply, deltas = g.chat_stream([{"role": "user", "content": "hi"}], model="m")
        got = [d async for d in deltas]
        await g.aclose()
        return reply, got

    reply, got = asyncio.run(go())
    assert got == ["Hel", "lo"]
    assert reply.text == "Hello"
    assert (reply.prompt_tokens, reply.completion_tokens) == (5, 2)
    assert reply.seconds >= 0
    assert seen_body["stream"] is True and seen_body["model"] == "m"
    assert seen_body["reasoning_effort"] == "none"
