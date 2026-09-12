"""The server-owned base stylesheet.

Gemma emits markup against this class vocabulary (plus, optionally, a small <style> of
page-specific rules). The server assembles the full document. Two views of every page:

  full document   = what is rendered, stored, and sent to the app. Has the real CSS in
                    <style id="sb-base">.
  model-facing    = the same document with that block's contents replaced by a one-line
                    comment, so prompts don't spend ~1.5k tokens re-reading CSS the
                    model must not touch anyway.

`inject()` turns a fragment or a stripped document into a full document. `strip()` does
the reverse. They round-trip.
"""

import re

STYLE_ID = "sb-base"
PLACEHOLDER = "/* base stylesheet, provided by the server; do not edit */"

BASE_CSS = """
:root{--bg:#f2f2f7;--surface:#fff;--surface-2:#f9f9fb;--text:#1c1c1e;--text-2:#6e6e73;--text-3:#aeaeb2;
--line:#e5e5ea;--accent:#007aff;--accent-2:#e5f0ff;--green:#34c759;--red:#ff3b30;--orange:#ff9500;--yellow:#ffcc00;
--purple:#af52de;--r:12px;--r-sm:8px;--r-lg:20px;--gap:12px;--pad:16px;--shadow:0 1px 3px rgba(0,0,0,.08),0 4px 16px rgba(0,0,0,.05)}
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;height:100%}
body{font:16px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Helvetica,Arial,sans-serif;
color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased;overflow:hidden}
h1,h2,h3,h4,p{margin:0}
h1{font-size:34px;font-weight:700;letter-spacing:-.4px;line-height:1.15}
h2{font-size:24px;font-weight:700;letter-spacing:-.3px}
h3{font-size:18px;font-weight:600}
h4{font-size:15px;font-weight:600}
.caption{font-size:13px;color:var(--text-2)}.muted{color:var(--text-2)}.small{font-size:13px}.bold{font-weight:600}
.link{color:var(--accent);text-decoration:none;font-weight:500}
.label{font-size:13px;font-weight:600;color:var(--text-2);text-transform:uppercase;letter-spacing:.4px}
a{color:inherit;text-decoration:none}

/* layout */
.screen{width:100vw;height:100vh;display:flex;flex-direction:column;background:var(--bg);overflow:hidden}
.screen.light{background:var(--surface)}
.split{display:flex;flex-direction:row;flex:1;min-height:0}.split>*{flex:1;min-width:0;min-height:0}
.split.screen,.screen.split{flex-direction:row}
.split.narrow-left>:first-child,.split.narrow-right>:last-child{flex:0 0 320px}
.sidebar{width:280px;flex:0 0 280px;background:var(--surface);border-right:1px solid var(--line);overflow:auto}
.stack{display:flex;flex-direction:column;gap:var(--gap)}.stack.split{flex-direction:row}
.row{display:flex;align-items:center;gap:var(--gap)}
.row.between{justify-content:space-between}.row.end{justify-content:flex-end}.wrap{flex-wrap:wrap}
.grid-2,.grid-3,.grid-4{display:grid;gap:var(--gap)}
.grid-2{grid-template-columns:repeat(2,1fr)}.grid-3{grid-template-columns:repeat(3,1fr)}.grid-4{grid-template-columns:repeat(4,1fr)}
.center{display:flex;align-items:center;justify-content:center}
.fill{flex:1;min-height:0;min-width:0}.scroll{overflow:auto}
.p{padding:var(--pad)}.p-lg{padding:24px}.p-xl{padding:40px}.px{padding-left:var(--pad);padding-right:var(--pad)}
.gap-sm{gap:6px}.gap-lg{gap:24px}.mt{margin-top:var(--gap)}.mt-lg{margin-top:24px}.mb{margin-bottom:var(--gap)}
.w-sm{max-width:360px;width:100%}.w-md{max-width:480px;width:100%}.w-lg{max-width:640px;width:100%}.mx-auto{margin-left:auto;margin-right:auto}
.spacer{flex:1}.divider{height:1px;background:var(--line);border:0;margin:0}
.text-center{text-align:center}

/* bars */
.nav-bar{height:56px;flex:0 0 56px;display:flex;align-items:center;gap:var(--gap);padding:0 var(--pad);
background:rgba(255,255,255,.92);border-bottom:1px solid var(--line);backdrop-filter:blur(10px)}
.nav-bar .title{font-size:17px;font-weight:600;flex:1;text-align:center}
.nav-bar.large{height:auto;flex-basis:auto;padding:12px var(--pad)}.nav-bar.large .title{font-size:34px;font-weight:700;text-align:left}
.tab-bar{height:64px;flex:0 0 64px;display:flex;background:rgba(255,255,255,.95);border-top:1px solid var(--line)}
.tab{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:11px;color:var(--text-2)}
.tab.active{color:var(--accent)}
.toolbar{display:flex;align-items:center;gap:var(--gap);padding:8px var(--pad);background:var(--surface);border-bottom:1px solid var(--line)}

/* controls */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:48px;padding:0 20px;border:0;border-radius:var(--r);
font:inherit;font-size:17px;font-weight:600;color:var(--text);background:var(--line);cursor:pointer;white-space:nowrap}
.btn-primary{background:var(--accent);color:#fff}.btn-secondary{background:var(--accent-2);color:var(--accent)}
.btn-ghost{background:transparent;color:var(--accent)}.btn-danger{background:var(--red);color:#fff}
.btn-outline{background:transparent;border:1.5px solid var(--line)}
.btn-block{width:100%;display:flex}.btn-sm{height:36px;padding:0 14px;font-size:15px;border-radius:var(--r-sm)}
.btn-round{width:48px;height:48px;padding:0;border-radius:50%}.btn-round.btn-outline{background:var(--surface)}
.input,.textarea,.select{width:100%;height:48px;padding:0 14px;border:1px solid var(--line);border-radius:var(--r);
background:var(--surface);font:inherit;color:var(--text);outline:0}
.input::placeholder{color:var(--text-3)}.textarea{height:auto;min-height:96px;padding:12px 14px;resize:none}
.field{display:flex;flex-direction:column;gap:6px}
.search{display:flex;align-items:center;gap:8px;height:40px;padding:0 12px;border-radius:10px;background:rgba(118,118,128,.12);color:var(--text-2)}
.search input{flex:1;border:0;background:transparent;font:inherit;outline:0}
.toggle{position:relative;display:inline-block;width:51px;height:31px;flex:0 0 51px}
.toggle input{opacity:0;width:0;height:0;margin:0}
.toggle span{position:absolute;inset:0;background:#e9e9ea;border-radius:31px;transition:.2s}
.toggle span::before{content:"";position:absolute;width:27px;height:27px;left:2px;top:2px;background:#fff;border-radius:50%;box-shadow:0 2px 4px rgba(0,0,0,.2);transition:.2s}
.toggle input:checked+span{background:var(--green)}.toggle input:checked+span::before{transform:translateX(20px)}
.checkbox{width:22px;height:22px;border:1.5px solid var(--text-3);border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex:0 0 22px}
.checkbox.on{background:var(--accent);border-color:var(--accent)}.checkbox.on::after{content:"";width:6px;height:11px;border:solid #fff;border-width:0 2px 2px 0;transform:translateY(-1px) rotate(45deg)}
.segmented{display:inline-flex;padding:2px;border-radius:9px;background:rgba(118,118,128,.12)}
.segmented button{border:0;background:transparent;font:inherit;font-size:13px;font-weight:600;padding:6px 16px;border-radius:7px;color:var(--text)}
.segmented button.active{background:var(--surface);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.slider{-webkit-appearance:none;width:100%;height:4px;border-radius:2px;background:var(--line);outline:0}
.slider::-webkit-slider-thumb{-webkit-appearance:none;width:28px;height:28px;border-radius:50%;background:#fff;box-shadow:0 2px 6px rgba(0,0,0,.25)}
.stepper{display:inline-flex;border-radius:var(--r-sm);background:var(--line);overflow:hidden}.stepper button{border:0;background:transparent;width:40px;height:32px;font-size:18px}

/* content */
.card{background:var(--surface);border-radius:var(--r-lg);padding:var(--pad);box-shadow:var(--shadow)}
.card.flat{box-shadow:none;border:1px solid var(--line)}.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--gap)}
.list{background:var(--surface);border-radius:var(--r);overflow:hidden}
.list-item{display:flex;align-items:center;gap:var(--gap);padding:12px var(--pad);min-height:56px;border-bottom:1px solid var(--line)}
.list-item:last-child{border-bottom:0}.list-item .fill{display:flex;flex-direction:column;gap:2px}
.list-item-title{font-weight:500}.list-item-sub{font-size:13px;color:var(--text-2)}
.chevron::after{content:"";width:9px;height:9px;border:solid var(--text-3);border-width:2px 2px 0 0;transform:rotate(45deg);margin-left:auto;flex:0 0 9px}
.avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#c7d2fe,#818cf8);flex:0 0 40px;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:600}
.avatar-sm{width:28px;height:28px;flex-basis:28px;font-size:12px}.avatar-lg{width:72px;height:72px;flex-basis:72px;font-size:26px}
.image,.image-hero,.image-square,.image-wide,.image-round{background:linear-gradient(135deg,#e2e8f0 0%,#cbd5e1 100%);border-radius:var(--r);min-height:120px;position:relative;overflow:hidden;flex:1}
.image::after,.image-hero::after,.image-square::after,.image-wide::after,.image-round::after{content:"";position:absolute;inset:0;background:radial-gradient(circle at 30% 30%,rgba(255,255,255,.55),transparent 55%)}
.image-hero{border-radius:0;min-height:100%;align-self:stretch}.image-square{aspect-ratio:1;min-height:0}.image-wide{aspect-ratio:16/9;min-height:0}.image-round{border-radius:50%;aspect-ratio:1;min-height:0;flex:0 0 auto}
.image>*,.image-hero>*,.image-square>*,.image-wide>*,.image-round>*{position:relative;z-index:1}
.chip{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 12px;border-radius:16px;background:var(--surface);border:1px solid var(--line);font-size:14px;font-weight:500}
.chip.active{background:var(--text);color:#fff;border-color:var(--text)}
.badge{display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:10px;background:var(--red);color:#fff;font-size:12px;font-weight:600}
.badge.accent{background:var(--accent)}.badge.green{background:var(--green)}.badge.soft{background:var(--accent-2);color:var(--accent)}
.progress{height:6px;border-radius:3px;background:var(--line);overflow:hidden}.progress>span{display:block;height:100%;background:var(--accent);border-radius:3px}
.stat{display:flex;flex-direction:column;gap:2px}.stat .value{font-size:28px;font-weight:700;letter-spacing:-.5px}.stat .caption{font-size:13px}
.hero-text{color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.35)}
.bar-chart{display:flex;align-items:flex-end;gap:8px;height:120px}.bar-chart>span{flex:1;background:var(--accent);border-radius:4px 4px 0 0;opacity:.85}

/* icons: 22px CSS-mask glyphs that take the text colour. <span class="icon icon-home"></span> */
.icon{display:inline-block;width:22px;height:22px;background:currentColor;flex:0 0 22px;
-webkit-mask:var(--i) center/contain no-repeat;mask:var(--i) center/contain no-repeat}
.icon-sm{width:16px;height:16px;flex-basis:16px}.icon-lg{width:28px;height:28px;flex-basis:28px}
.icon-home{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 3 2 12h3v8h5v-6h4v6h5v-8h3z'/%3E%3C/svg%3E")}
.icon-search{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M10 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16zm0 3a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm6.5 10 6 6-2.5 2.5-6-6z'/%3E%3C/svg%3E")}
.icon-user{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='8' r='5'/%3E%3Cpath d='M3 22c0-5 4-8 9-8s9 3 9 8z'/%3E%3C/svg%3E")}
.icon-heart{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 21 3.5 12.5A5 5 0 0 1 12 6a5 5 0 0 1 8.5 6.5z'/%3E%3C/svg%3E")}
.icon-plus{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M10.5 3h3v7.5H21v3h-7.5V21h-3v-7.5H3v-3h7.5z'/%3E%3C/svg%3E")}
.icon-close{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M5 3 3 5l7 7-7 7 2 2 7-7 7 7 2-2-7-7 7-7-2-2-7 7z'/%3E%3C/svg%3E")}
.icon-back{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M15 3 5 12l10 9 2-2.2L10 12l7-6.8z'/%3E%3C/svg%3E")}
.icon-chevron{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 3l10 9-10 9-2-2.2L14 12 7 5.2z'/%3E%3C/svg%3E")}
.icon-bell{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2a6 6 0 0 0-6 6v4l-2 4h16l-2-4V8a6 6 0 0 0-6-6zm-3 17a3 3 0 0 0 6 0z'/%3E%3C/svg%3E")}
.icon-star{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='m12 2 3 7 7 .6-5.3 4.8L18.5 22 12 18l-6.5 4 1.8-7.6L2 9.6 9 9z'/%3E%3C/svg%3E")}
.icon-settings{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm-2-6h4l.6 3 2.6 1.5 2.9-1 2 3.5-2.3 2v3l2.3 2-2 3.5-2.9-1L14.6 21l-.6 3h-4l-.6-3-2.6-1.5-2.9 1-2-3.5 2.3-2v-3L1.9 9l2-3.5 2.9 1L9.4 5z'/%3E%3C/svg%3E")}
.icon-cart{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2 3h3l3 11h11l3-8H7.5M9 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm9 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z' stroke='black' stroke-width='2' fill='none'/%3E%3C/svg%3E")}
.icon-mail{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2 5h20v14H2zm2 2v1l8 5 8-5V7z'/%3E%3C/svg%3E")}
.icon-camera{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 4h6l1.5 2.5H21v13H3v-13h4.5zM12 9a4 4 0 1 0 0 8 4 4 0 0 0 0-8z'/%3E%3C/svg%3E")}
.icon-menu{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M3 5h18v2.5H3zm0 5.75h18v2.5H3zM3 16.5h18V19H3z'/%3E%3C/svg%3E")}
.icon-more{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='5' cy='12' r='2.2'/%3E%3Ccircle cx='12' cy='12' r='2.2'/%3E%3Ccircle cx='19' cy='12' r='2.2'/%3E%3C/svg%3E")}
.icon-check{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='m4 12 2.2-2.2 3.8 3.8 8-8L20 7.8l-10 10z'/%3E%3C/svg%3E")}
.icon-play{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M6 3l15 9-15 9z'/%3E%3C/svg%3E")}
.icon-calendar{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M3 5h18v16H3zm2 5v9h14v-9zM7 2h2v4H7zm8 0h2v4h-2z'/%3E%3C/svg%3E")}
.icon-apple{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M16.5 12.6c0-2.4 2-3.5 2-3.6-1.1-1.6-2.8-1.8-3.4-1.8-1.5-.2-2.8.8-3.6.8-.7 0-1.8-.8-3-.8C7 7.3 5.5 8.2 4.7 9.6c-1.8 3.1-.5 7.6 1.3 10.1.8 1.2 1.8 2.6 3.1 2.5 1.3 0 1.7-.8 3.3-.8 1.5 0 1.9.8 3.3.8 1.4 0 2.2-1.2 3-2.4.9-1.4 1.3-2.7 1.4-2.8-.1 0-3.6-1.3-3.6-4.4zM14 5.3c.7-.8 1.1-2 1-3.2-1 0-2.2.7-2.9 1.5-.6.7-1.2 1.9-1 3 1.1.1 2.2-.5 2.9-1.3z'/%3E%3C/svg%3E")}
.icon-google{--i:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2a10 10 0 1 0 9.8 12H12v-4h9.8A10 10 0 0 0 12 2zm0 3a7 7 0 0 1 4.6 1.7l-2.3 2.3A4 4 0 1 0 15.7 14H12v-3h7a7 7 0 1 1-7-6z'/%3E%3C/svg%3E")}
""".strip()

_BASE_BLOCK = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.DOTALL)
_HEAD_OPEN = re.compile(r"<head[^>]*>", re.IGNORECASE)
_HTML_OPEN = re.compile(r"<html[^>]*>", re.IGNORECASE)


def base_block(css: str = BASE_CSS) -> str:
    return f'<style id="{STYLE_ID}">{css}</style>'


def strip(html: str) -> str:
    """Full document -> model-facing document (base CSS replaced by a comment)."""
    return _BASE_BLOCK.sub(base_block(PLACEHOLDER), html, count=1)


def inject(html: str) -> str:
    """Fragment or model-facing document -> full document with the real base CSS."""
    if _BASE_BLOCK.search(html):
        return _BASE_BLOCK.sub(lambda _: base_block(), html, count=1)
    if _HTML_OPEN.search(html):
        # A full document without our block (the model ignored the fragment rule).
        # Put the base CSS first in <head> so the page's own <style> still wins.
        m = _HEAD_OPEN.search(html)
        if m:
            return html[:m.end()] + base_block() + html[m.end():]
        m = _HTML_OPEN.search(html)
        return html[:m.end()] + "<head>" + base_block() + "</head>" + html[m.end():]
    # A fragment: optional <style> plus body markup.
    return ("<!doctype html><html><head>"
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            + base_block() + "</head><body>" + html.strip() + "</body></html>")


# What the model is told. Every class here exists in BASE_CSS. Keep the two in sync.
GUIDE = """A base stylesheet is already loaded. Build screens from these classes (do not redefine them):

LAYOUT  .screen (fills the viewport; flex column; add .light for a white background)  .split (side-by-side children; .narrow-left / .narrow-right make one side 320px)  .sidebar  .stack (vertical, 12px gaps)  .row (horizontal, centered; add .between / .end / .wrap)  .grid-2 .grid-3 .grid-4  .center  .fill (grow)  .scroll  .spacer  .p .p-lg .p-xl (padding)  .gap-sm .gap-lg  .mt .mt-lg .mb  .w-sm .w-md .w-lg + .mx-auto (constrained centered column)  .divider  .text-center
BARS    .nav-bar with .title (add .large for a big left title)  .tab-bar > .tab (add .active) each with an .icon and a label  .toolbar
TEXT    h1 h2 h3 h4 p  .caption .muted .small .bold .label .link  .hero-text (white text over an image)
CONTROLS  .btn + one of .btn-primary .btn-secondary .btn-ghost .btn-outline .btn-danger; modifiers .btn-block .btn-sm .btn-round  |  .input .textarea .select (inside a .field with a .label)  |  .search containing an .icon-search and an <input>  |  label.toggle > input[type=checkbox] + span  |  .checkbox (.on)  |  .segmented > button (.active)  |  input.slider  |  .stepper
CONTENT .card (.flat) with .card-header  |  .list > .list-item (with an .avatar or .icon, a .fill holding .list-item-title + .list-item-sub, and .chevron on the item for a disclosure arrow)  |  .avatar (.avatar-sm .avatar-lg; put initials inside)  |  .image = photo placeholder (.image-hero fills its parent, .image-square, .image-wide, .image-round); put .hero-text inside for captions  |  .chip (.active)  .badge (.accent .green .soft)  .progress > span[style=width]  .stat with .value + .caption  .bar-chart > span[style=height]
ICONS   <span class="icon icon-NAME"></span> (.icon-sm .icon-lg) where NAME is one of: home search user heart plus close back chevron bell star settings cart mail camera menu more check play calendar apple google
COLORS  CSS variables --accent --green --red --orange --yellow --purple --text --text-2 --line --surface --bg; use them in inline styles or a small <style>."""
