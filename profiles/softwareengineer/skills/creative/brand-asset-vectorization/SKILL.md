---
name: brand-asset-vectorization
description: "Trace a raster logo into SVG, favicon set, brand icons."
version: 1.0.0
author: softwareengineer
license: MIT
dependencies: []
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [logo, favicon, SVG, brand, vectorization, icons, design, nextjs]
    related_skills: [architecture-diagram, claude-design]
---

# Brand Asset Vectorization

## When to Use

Trigger when the user supplies a **picture** of a logo (screenshot, JPG/PNG, sketch, a
photo of a printout) and asks to put it on a site or app:

- "ubah logo pada mesin pencari / header jadi seperti ini"
- "turn this into the favicon", "use this as the app icon"
- "match this brand mark", "recreate this logo"
- a logo keeps rendering wrong or blurry and needs a vector replacement

The deliverable is a **faithful vector** that survives at 16px and in a production build,
not an approximation that merely looks logo-ish.

**Not for:** generating a new logo from a written description (use a design skill), or
architecture/infographic diagrams (`architecture-diagram`, `baoyu-infographic`).

## Non-negotiables

1. **Measure, never eyeball.** Sample the reference's real colours and geometry with
   Python before writing a single coordinate. Eyeballed proportions are wrong ~every time.
2. **Never trust a vision model's proportion judgement.** Vision will confidently say
   "the letters are too big / the shield is too small" when pixel measurement proves the
   opposite. Use vision for *identification* (what shape is this, are these letters, is the
   outline continuous, where is the gap) and pixel stats for *proportion and colour*.
   When the two disagree, the pixels win.
3. **Read the glyphs off the artwork, then say what you read.** Confirm the actual letters
   by zooming the crop. Do not assume the monogram matches the brand-name initials — a mark
   may read `WN` while the site is "Warta Nusantara" and you guessed `WNT`. If your reading
   contradicts the obvious guess, tell the user explicitly and offer the alternative.
4. **Inline SVG in the component.** No extra HTTP request, crisp at every size, brand
   colours as literals so a stray `fill` cannot override them. One `size` prop, square
   artwork.
5. **Crossing glyphs need a knockout pass, not z-order.** When letters cross a frame line
   and the design shows a white gap, draw the frame, then a white stroke of the glyph
   geometry *wider than the frame stroke*, then the solid glyphs on top. Reordering alone
   will not open the gap.

## Procedure

### 1. Measure the reference

```bash
pip install --quiet pillow numpy   # scratch venv is fine
python3 scripts/measure-artwork.py path/to/logo.jpg
```

The script prints, per colour class: pixel count, **mean RGB = the exact brand colour**
(use it verbatim — `#CFA53F` from `(207.8, 165.5, 63.2)`, do not round to a "nicer" gold),
and the bbox. Then it prints every measurement normalised to a 0..200 viewBox.

Go further on structure: slice the mask **per column and per row** and print run lengths.
That reveals wall positions, where the outline breaks, and how many stroke runs a row has —
detail no screenshot inspection recovers.

### 2. Write the SVG in a 200x200 viewBox

Normalise everything to `viewBox="0 0 200 200"`. Coordinates become readable and are
direct arithmetic from the percentages above.

### 3. Iterate by rendering, not by imagining

Write a throwaway preview HTML that renders the candidate **beside the reference at the
same height**, open it in the browser tool, and read it back. Keep it ephemeral, in scratch
space. After each candidate, re-run the pixel metrics on *your own render* and compare:

```python
print('inkW/goldW %.3f' % ((xi.max()-xi.min())/(xg.max()-xg.min())))
```

Match within ~5% and stop — chasing the last 3% is not worth the turns.

### 4. Check for hairline defects numerically

Do not squint at a zoom. Flood-fill from the border and count enclosed white pixels: any
interior white region inside a solid glyph is a seam bug. `scripts/measure-artwork.py`
reports this as its hole check.

**Seam rule:** adjacent letter paths that merely *abut* leave a hairline. Start the second
path a unit *inside* the first so the fills overlap.

**Anti-aliasing false positive:** a reported hole whose pixels are mid-grey (~99–133, not
~255) at a counter edge is AA noise. Print the flagged pixel colours before "fixing" a
non-problem.

### 5. Ship the icon set

Full artwork collapses to a blob at 16px. Generate a **simplified variant** for small
sizes: heavier frame stroke, no knockout halo, glyphs inset ~0.86x so they do not bleed off
the canvas. See `references/favicon-pipeline.md` for the complete sharp-based generator
(ICO container writer, Next.js app-router conventions, metadata block, staging-port
verification).

## Pitfalls

- **Vision calls time out on large crops.** Ask a one-line question or pass a smaller
  image; do not conclude the artwork is unreadable and start over.
- **Never call a colour "wrong" from a small screenshot.** At 44px a gold stroke is 2px
  wide and a viewer reports "the logo is black". Verify real values in the DOM with
  `getComputedStyle(p).stroke` before changing anything — the DOM does not lie.
- **A referenced asset that does not exist is a silent bug.** Check whether a `logo.png`
  cited by JSON-LD / OG tags actually resolves. Structured data pointing at a 404 breaks
  the publisher entity for crawlers while the page still looks perfect.
- **Add generator dependencies explicitly.** A script requiring `sharp` must list it in
  `devDependencies`, pinned to what `npm ls` reports — not to a guessed range. A transitive
  dep vanishes on a clean install.
- **Re-run the generator to prove determinism**, then commit the generated binaries.

## Before you present it

State which glyphs you read off the artwork and flag any mismatch with the brand name —
the one thing pixel maths cannot settle.
