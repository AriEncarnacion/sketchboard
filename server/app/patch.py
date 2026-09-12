"""Search/replace patches for follow-up edits.

The model answers an edit with one or more blocks:

    <<<<<<< SEARCH
    exact lines copied from the current document
    =======
    replacement lines
    >>>>>>> REPLACE

`parse()` pulls the blocks out of a reply; `apply()` applies them in order. A block
matches exactly first, then with whitespace normalised per line (models drift on
indentation). If any block fails, the whole patch fails and the caller falls back to a
full rewrite, so a half-applied edit never reaches the user.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_BLOCK = re.compile(
    r"<{7} *SEARCH[ \t]*\n(?P<search>.*?)\n?={7}[ \t]*\n(?P<replace>.*?)\n?>{7} *REPLACE",
    re.DOTALL,
)


@dataclass
class Hunk:
    search: str
    replace: str


def parse(text: str) -> list[Hunk]:
    return [Hunk(m.group("search"), m.group("replace")) for m in _BLOCK.finditer(text)]


def _find_loose(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate `needle` in `haystack` comparing lines with surrounding whitespace stripped.
    Returns the exact character span in `haystack` to replace, or None."""
    h_lines = haystack.split("\n")
    n_lines = [l.strip() for l in needle.split("\n")]
    while n_lines and not n_lines[-1]:
        n_lines.pop()
    while n_lines and not n_lines[0]:
        n_lines.pop(0)
    if not n_lines:
        return None
    stripped = [l.strip() for l in h_lines]
    for i in range(len(h_lines) - len(n_lines) + 1):
        if stripped[i:i + len(n_lines)] == n_lines:
            start = sum(len(l) + 1 for l in h_lines[:i])
            end = start + sum(len(l) + 1 for l in h_lines[i:i + len(n_lines)]) - 1
            return start, end
    return None


FUZZY_MIN_RATIO = 0.92


def _find_fuzzy(haystack: str, needle: str) -> tuple[int, int] | None:
    """Last resort: the model retyped a line slightly wrong (a missing semicolon, a colour
    written in a different case). Slide a window of the same line count over the document
    and accept the best window if it is at least FUZZY_MIN_RATIO similar with whitespace
    collapsed. Only used when exact and loose matching both fail."""
    n_lines = [l.strip() for l in needle.strip("\n").split("\n")]
    if not n_lines:
        return None
    h_lines = haystack.split("\n")
    target = " ".join(n_lines).lower()   # HTML tags and CSS hex colours are case-insensitive
    best, best_i = 0.0, -1
    sm = SequenceMatcher(autojunk=False)
    sm.set_seq2(target)
    for i in range(len(h_lines) - len(n_lines) + 1):
        window = " ".join(l.strip() for l in h_lines[i:i + len(n_lines)]).lower()
        if abs(len(window) - len(target)) > max(8, len(target) // 4):
            continue
        sm.set_seq1(window)
        r = sm.ratio()
        if r > best:
            best, best_i = r, i
    if best < FUZZY_MIN_RATIO:
        return None
    start = sum(len(l) + 1 for l in h_lines[:best_i])
    end = start + sum(len(l) + 1 for l in h_lines[best_i:best_i + len(n_lines)]) - 1
    return start, end


def apply(html: str, hunks: list[Hunk]) -> tuple[str | None, str]:
    """Apply hunks in order. Returns (new_html, note). new_html is None on failure and
    the note says which hunk failed."""
    if not hunks:
        return None, "no hunks"
    out = html
    for i, h in enumerate(hunks, 1):
        if not h.search.strip():
            return None, f"hunk {i}: empty search"
        pos = out.find(h.search)
        if pos != -1:
            # Exact match, possibly mid-line (model omitted the indentation). Carry that
            # line's indentation onto any replacement lines that have none of their own.
            line_start = out.rfind("\n", 0, pos) + 1
            prefix = out[line_start:pos]
            repl = h.replace
            if prefix and prefix.isspace() and "\n" in repl:
                lines = repl.split("\n")
                repl = "\n".join([lines[0]] + [(l if not l or l[0].isspace() else prefix + l) for l in lines[1:]])
            out = out[:pos] + repl + out[pos + len(h.search):]
            continue
        span = _find_loose(out, h.search) or _find_fuzzy(out, h.search)
        if span is None:
            return None, f"hunk {i}: search text not found: {h.search.strip()[:90]!r}"
        # Re-indent the replacement to match the matched region's first line.
        indent = re.match(r"[ \t]*", out[span[0]:]).group(0)
        repl_lines = h.replace.split("\n")
        first_indent = re.match(r"[ \t]*", repl_lines[0]).group(0) if repl_lines else ""
        repl = "\n".join(
            (indent + l[len(first_indent):]) if l.startswith(first_indent) else l for l in repl_lines
        )
        out = out[:span[0]] + repl + out[span[1]:]
    if out == html:
        return None, "patch made no change"
    return out, f"{len(hunks)} hunk(s) applied"
