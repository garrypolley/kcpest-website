#!/usr/bin/env python3
"""
Print layout metrics for the 178×52 official logo (WebP/PNG) — use when tuning SiteLogo.astro.

  python3 scripts/logo-layout-validate.py

Requires: pillow, numpy
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "public/images/brand/kc-pest-header-logo.webp"


def main() -> None:
    if not REF.exists():
        print("Missing", REF, file=sys.stderr)
        sys.exit(1)
    im = np.array(Image.open(REF).convert("RGBA"))
    h, w = im.shape[:2]
    a = im[:, :, 3] > 128
    sub = a[:, 54:]
    for name, y0, y1 in [("KC PEST", 9, 28), ("EXPERTS", 32, 43)]:
        block = sub[y0 : y1 + 1, :]
        ys, xs = np.where(block)
        if len(xs) == 0:
            continue
        print(
            f"{name}: x {xs.min()+54}–{xs.max()+54}  y {ys.min()+y0}–{ys.max()+y0}  "
            f"width {xs.max()-xs.min()+1}"
        )
    print("canvas:", w, "×", h)
    print("icon: columns 0–45; gap 46–53; text from x≥54")


if __name__ == "__main__":
    main()
