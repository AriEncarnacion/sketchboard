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

CRITIQUE = """The first image is the original hand-drawn sketch. The second image is a screenshot of the current mockup rendered at {width}x{height}.

Designer's notes: {description}

Compare the render to the sketch. Check:
- Same elements present, in the same positions and relative sizes.
- Nothing overflowing, overlapping, clipped, or off-screen.
- Text legible, spacing consistent, looks like a finished product screen.

If the render is a faithful, polished version of the sketch, reply with exactly the single word APPROVED and nothing else.

Otherwise, list the concrete problems in 2-5 bullets, then output the COMPLETE corrected HTML document in a ```html block. Fix the layout issues; do not redesign what already matches."""

REPAIR = """Your previous reply did not contain a complete HTML document.
Output the complete mockup now as ONE ```html fenced block containing <!doctype html> through </html>. No commentary."""
