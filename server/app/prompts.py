"""Prompts for the draft / critique loop. Kept in one place so they're easy to tune."""

SYSTEM = """You are a senior product designer and front-end engineer.
You turn rough hand-drawn UI sketches into polished, high-fidelity mockups.

Output rules:
- Produce ONE complete, self-contained HTML document: <!doctype html> through </html>.
- All CSS inline in a <style> tag. No external stylesheets, fonts, scripts, or images.
- Use system fonts (-apple-system, "SF Pro", Helvetica, Arial). Use CSS for icons and shapes; no emoji as icons.
- Design for an iPad in landscape at {width}x{height} CSS px. Fill that viewport; no page scrolling unless the sketch clearly shows a scrolling list.
- Use realistic placeholder content (names, prices, labels), not lorem ipsum.
- Respect the sketch's layout, hierarchy, and element positions. Boxes with an X are images. Squiggles are text. Circles are avatars or buttons depending on context.
- Where the sketch is ambiguous, choose the conventional iOS/iPadOS pattern.
- Put the HTML in a single ```html fenced code block and nothing else."""

DRAFT = """Here is a hand-drawn sketch of a screen.

Designer's notes: {description}

First, in 3-6 short bullet points, list the UI elements you see and their arrangement.
Then output the complete HTML mockup in a ```html block."""

# Step 1 of the loop: a short verdict, no HTML. Cheap (~100 output tokens).
JUDGE = """Image 1 above is the original hand-drawn sketch. Image 2 above is a screenshot of the current mockup rendered at {width}x{height}. Both are attached.

Designer's notes: {description}
{checks}
Compare the render to the sketch:
- Are the same elements present, in the same positions and relative sizes?
- Is anything overflowing, overlapping, clipped, or off-screen?
- Is the text legible and the spacing consistent? Does it look like a finished product screen?

Do NOT output any HTML.
If the render is a faithful, polished version of the sketch and the automated checks found nothing, reply with exactly the single word APPROVED.
Otherwise reply with a bullet list of the concrete problems (at most 5, one line each, specific: which element, what is wrong, what it should be). Only list problems that matter; cosmetic taste is not a problem."""

# Step 2, only when the judge found problems: revise the previous HTML.
REVISE = """Here is the current mockup HTML:

```html
{html}
```

A review found these problems:
{problems}

Fix exactly these problems. Keep everything else as it is. Output the COMPLETE corrected HTML document in one ```html block and nothing else."""

CHECKS_HEADER = "\nAutomated layout checks found these problems (measured in the browser, they are facts, include all of them):\n"
CHECKS_CLEAN = "\nAutomated layout checks passed: nothing overflows the viewport, no tiny text, no external resources.\n"

# Follow-up edit on an existing mockup. The sketch is attached again for context.
EDIT = """Here is the current mockup HTML:

```html
{html}
```

The original hand-drawn sketch is attached for reference. Designer's notes: {description}
{history}
The designer now asks: "{instruction}"

Apply exactly that change. Keep everything else as it is. Output the COMPLETE updated HTML document in one ```html block and nothing else."""

EDIT_HISTORY = "\nEarlier edits already applied, in order:\n{items}\n"

REPAIR = """Your previous reply did not contain a complete HTML document.
Output the complete mockup now as ONE ```html fenced block containing <!doctype html> through </html>. No commentary."""
