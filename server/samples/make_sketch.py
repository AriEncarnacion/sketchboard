"""Generate fake hand-drawn UI sketches for testing. Needs Pillow.

    python3 samples/make_sketch.py            # writes samples/<name>.png for every sketch
    python3 samples/make_sketch.py login      # just one

Each sketch has a one-line description in DESCRIPTIONS, the text a user might dictate.
"""

import random
import sys

from PIL import Image, ImageDraw

W, H = 1180, 820
INK = (40, 40, 60)
PAPER = (250, 248, 244)


def wobble(p, amt=3):
    return (p[0] + random.uniform(-amt, amt), p[1] + random.uniform(-amt, amt))


def line(d, a, b, width=4):
    steps = max(2, int(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / 25))
    pts = [wobble((a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)) for i in range(steps + 1)]
    d.line(pts, fill=INK, width=width, joint="curve")


def rect(d, x0, y0, x1, y1, width=4):
    line(d, (x0, y0), (x1, y0), width); line(d, (x1, y0), (x1, y1), width)
    line(d, (x1, y1), (x0, y1), width); line(d, (x0, y1), (x0, y0), width)


def image_box(d, x0, y0, x1, y1):
    rect(d, x0, y0, x1, y1)
    line(d, (x0, y0), (x1, y1)); line(d, (x1, y0), (x0, y1))


def squiggle(d, x, y, length, amp=5):
    pts = [(x + i, y + amp * (1 if (i // 8) % 2 else -1) + random.uniform(-1, 1)) for i in range(0, length, 4)]
    d.line(pts, fill=INK, width=3)


def text(d, x, y, s, size=30):
    d.text((x, y), s, fill=INK, font_size=size)


def circle(d, cx, cy, r, width=4):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=width)


def toggle(d, x, y):
    d.rounded_rectangle((x, y, x + 70, y + 36), radius=18, outline=INK, width=4)
    circle(d, x + 52, y + 18, 13)


def login(d):
    image_box(d, 80, 80, 560, 740)
    text(d, 700, 120, "Welcome back")
    squiggle(d, 700, 180, 300)
    rect(d, 700, 260, 1100, 320); text(d, 720, 272, "email")
    rect(d, 700, 350, 1100, 410); text(d, 720, 362, "password")
    rect(d, 700, 460, 1100, 530, width=6); text(d, 850, 478, "Log in")
    squiggle(d, 760, 600, 280, amp=3)
    text(d, 720, 620, "forgot password?")
    for cx in (780, 900, 1020):
        circle(d, cx, 710, 30)


def settings(d):
    # nav bar with back chevron and title
    line(d, (60, 40), (1120, 40))
    line(d, (60, 120), (1120, 120))
    line(d, (100, 80), (80, 60)); line(d, (80, 60), (100, 40))
    text(d, 480, 60, "Settings", size=34)
    # section label
    text(d, 90, 160, "ACCOUNT", size=22)
    # rows: avatar + name, then three toggle rows, then a red-ish "sign out"
    circle(d, 130, 250, 36)
    text(d, 200, 225, "Alex Rivera", size=28); squiggle(d, 200, 275, 260, amp=3)
    line(d, (160, 300), (1100, 300), width=2)
    y = 340
    for label in ("Notifications", "Dark mode", "Face ID"):
        text(d, 90, y, label, size=28)
        toggle(d, 1000, y - 2)
        line(d, (90, y + 60), (1100, y + 60), width=2)
        y += 90
    text(d, 90, 640, "PRIVACY", size=22)
    text(d, 90, 690, "Location", size=28); text(d, 940, 690, "Always  >", size=28)
    line(d, (90, 750), (1100, 750), width=2)


def product_grid(d):
    # search bar, then 2x3 grid of product cards: image, title squiggle, price
    rect(d, 60, 40, 1000, 100); text(d, 90, 52, "search", size=26)
    circle(d, 1080, 70, 26)
    x0s, y0s = (60, 440, 820), (150, 500)
    prices = ("$24", "$89", "$12", "$45", "$130", "$8")
    i = 0
    for y0 in y0s:
        for x0 in x0s:
            image_box(d, x0, y0, x0 + 300, y0 + 200)
            squiggle(d, x0 + 10, y0 + 240, 220, amp=3)
            text(d, x0 + 10, y0 + 262, prices[i], size=26)
            circle(d, x0 + 270, y0 + 275, 18)
            i += 1


def chat(d):
    # nav bar: avatar + name; bubbles alternating; input bar with send circle
    line(d, (60, 110), (1120, 110))
    circle(d, 120, 60, 32); text(d, 180, 40, "Sam", size=30)
    bubbles = [(80, 150, 520, 220), (640, 250, 1100, 320), (80, 350, 460, 400),
               (560, 430, 1100, 540), (80, 570, 600, 640)]
    for (x0, y0, x1, y1) in bubbles:
        d.rounded_rectangle((x0, y0, x1, y1), radius=28, outline=INK, width=4)
        squiggle(d, x0 + 24, (y0 + y1) // 2, x1 - x0 - 48, amp=3)
    rect(d, 60, 700, 1020, 780); text(d, 90, 718, "message", size=26)
    circle(d, 1080, 740, 34)
    line(d, (1066, 740), (1096, 740), width=3); line(d, (1084, 728), (1096, 740), width=3); line(d, (1084, 752), (1096, 740), width=3)


SKETCHES = {"login": login, "settings": settings, "product_grid": product_grid, "chat": chat}

DESCRIPTIONS = {
    "login": "login screen. big product photo on the left, form on the right, three social sign-in buttons at the bottom",
    "settings": "settings screen for a fitness app. account section with profile row and toggles, then a privacy section",
    "product_grid": "shop screen for a plant store. search bar on top, grid of products with photo, name, price and a heart to favorite",
    "chat": "chat conversation with a friend named Sam, message bubbles, input bar at the bottom with a send button",
}


def make(name: str, out: str) -> None:
    random.seed(hash(name) % 1000)
    img = Image.new("RGB", (W, H), PAPER)
    SKETCHES[name](ImageDraw.Draw(img))
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    names = sys.argv[1:] or list(SKETCHES)
    for n in names:
        make(n, f"samples/{n}.png")
