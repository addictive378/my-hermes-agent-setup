#!/usr/bin/env python3
"""Measure a raster logo into proportions you can draw an SVG from.

Usage:  python3 measure-artwork.py path/to/logo.jpg

Reports, for each colour class (warm gold, charcoal ink): pixel count, mean RGB
(the exact brand colours) and bbox. Then reports every measurement normalised to
a 0..200 viewBox, which is what you plug into a `0 0 200 200` viewBox.

Finish with an enclosed-white-pixel check, for validating YOUR OWN render for
hairline seams.

Requires: pillow, numpy
    pip install --quiet pillow numpy
"""
import sys
from collections import Counter, deque

import numpy as np
from PIL import Image


def classify(a):
    """Boolean masks for a gold-like warm stroke and a charcoal ink fill."""
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    gold = (R > 140) & (R < 235) & (G > 110) & (G < 200) & (B < 130)
    ink = (R < 100) & (G < 100) & (B < 110)
    return {"gold": gold, "ink": ink}


def interior_holes(mask):
    """White pixels fully enclosed by mask -> seam defects in your own render."""
    H, W = mask.shape
    white = ~mask
    seen = np.zeros((H, W), bool)
    q = deque()
    for x in range(W):
        for y in (0, H - 1):
            if white[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(H):
        for x in (0, W - 1):
            if white[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and white[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return white & ~seen


def main(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(int)
    masks = classify(a)
    print(f"image: {im.size[0]}x{im.size[1]}")

    for name, m in masks.items():
        ys, xs = np.where(m)
        if not len(xs):
            print(f"{name}: none found (adjust thresholds)")
            continue
        mean = a[m].mean(axis=0).round(1)
        hexcol = "#%02X%02X%02X" % (int(mean[0]), int(mean[1]), int(mean[2]))
        print(f"{name}: {int(m.sum())} px  mean rgb {tuple(mean)}  hex {hexcol}")
        print(f"   bbox x {xs.min()}..{xs.max()}  y {ys.min()}..{ys.max()}")

    union = masks["gold"] | masks["ink"]
    ys, xs = np.where(union)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    W, H = x1 - x0, y1 - y0
    print(f"\nunion bbox: x {x0}..{x1} ({W})  y {y0}..{y1} ({H})")

    yi, xi = np.where(masks["ink"])
    yg, xg = np.where(masks["gold"])
    if len(xi) and len(xg):
        print("\n--- normalised to 0..200 for the viewBox ---")
        print(f"inkW/goldW      {(xi.max()-xi.min())/(xg.max()-xg.min()):.3f}")
        print(f"inkH/artH       {(yi.max()-yi.min())/H*100:.1f}%")
        print(f"ink band        {(yi.min()-y0)/H*100:.1f}% .. {(yi.max()-y0)/H*100:.1f}%")
        print(f"ink x           {(xi.min()-x0)/W*200:.1f} .. {(xi.max()-x0)/W*200:.1f}")
        print(f"gold x          {(xg.min()-x0)/W*200:.1f} .. {(xg.max()-x0)/W*200:.1f}")
        print(f"gold y          {(yg.min()-y0)/H*200:.1f} .. {(yg.max()-y0)/H*200:.1f}")

    print("\n--- row run-length dump (structure: counter/gap positions) ---")
    for y in range(y0, y1 + 1, max(1, H // 12)):
        row = np.where(union[y])[0]
        if not len(row):
            continue
        runs, s, p = [], row[0], row[0]
        for v in row[1:]:
            if v > p + 1:
                runs.append((int(s), int(p)))
                s = v
            p = v
        runs.append((int(s), int(p)))
        print(f"   y={y:4d}  {runs[:8]}")

    print("\n--- dominant colours ---")
    small = im.resize((160, 160))
    for col, n in Counter(small.getdata()).most_common(6):
        print(f"   {col}  {n}")

    holes = interior_holes(masks["ink"])
    print(f"\ninterior white px (hole check): {int(holes.sum())}")
    hy, hx = np.where(holes)
    if len(hy):
        print("   flagged pixel colours:", [tuple(a[y, x]) for y, x in list(zip(hy, hx))[:5]])
        print("   mid-grey ~99..133 at a counter edge = anti-aliasing, NOT a defect")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
