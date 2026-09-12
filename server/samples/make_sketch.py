"""Generate a fake hand-drawn login-screen sketch for testing. Needs Pillow.

    python3 samples/make_sketch.py samples/login.png
"""

import random
import sys

from PIL import Image, ImageDraw

random.seed(7)
W, H = 1180, 820
INK = (40, 40, 60)


def wobble(p, amt=3):
    return (p[0] + random.uniform(-amt, amt), p[1] + random.uniform(-amt, amt))


def line(d, a, b, width=4):
    steps = max(2, int(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / 25))
    pts = [wobble((a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)) for i in range(steps + 1)]
    d.line(pts, fill=INK, width=width, joint="curve")


def rect(d, x0, y0, x1, y1, width=4):
    line(d, (x0, y0), (x1, y0), width); line(d, (x1, y0), (x1, y1), width)
    line(d, (x1, y1), (x0, y1), width); line(d, (x0, y1), (x0, y0), width)


def squiggle(d, x, y, length, amp=5):
    pts = [(x + i, y + amp * (1 if (i // 8) % 2 else -1) + random.uniform(-1, 1)) for i in range(0, length, 4)]
    d.line(pts, fill=INK, width=3)


def scribble_text(d, x, y, text):
    d.text((x, y), text, fill=INK, font_size=30)


def main(out: str) -> None:
    img = Image.new("RGB", (W, H), (250, 248, 244))
    d = ImageDraw.Draw(img)
    # left: hero image box with an X
    rect(d, 80, 80, 560, 740)
    line(d, (80, 80), (560, 740)); line(d, (560, 80), (80, 740))
    # right: login form
    scribble_text(d, 700, 120, "Welcome back")
    squiggle(d, 700, 180, 300)
    rect(d, 700, 260, 1100, 320); scribble_text(d, 720, 272, "email")
    rect(d, 700, 350, 1100, 410); scribble_text(d, 720, 362, "password")
    rect(d, 700, 460, 1100, 530, width=6); scribble_text(d, 850, 478, "Log in")
    squiggle(d, 760, 600, 280, amp=3)
    scribble_text(d, 720, 620, "forgot password?")
    # social buttons row: three circles
    for cx in (780, 900, 1020):
        d.ellipse((cx - 30, 680, cx + 30, 740), outline=INK, width=4)
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "samples/login.png")
