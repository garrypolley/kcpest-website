#!/usr/bin/env python3
"""
Compare two raster images numerically (pixel RGB). Resizes image B to match image A using LANCZOS.
Supports PNG or WebP (anything Pillow opens).

Usage:
  python3 scripts/compare_png.py path/to/reference.png path/to/candidate.webp

Exits 0 always; prints MAE, RMSE, max channel diff, % pixels with any channel > 10.
Useful when iterating on exports or screenshots vs the canonical header asset.

Requires: pillow
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: compare_png.py reference.png candidate.png", file=sys.stderr)
        sys.exit(2)
    a_path = Path(sys.argv[1])
    b_path = Path(sys.argv[2])
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    aw = a.tobytes()
    bw = b.tobytes()
    n = len(aw)
    assert n == len(bw) and n % 3 == 0
    px = n // 3
    diff_sum = 0.0
    diff_sq = 0.0
    max_d = 0
    bad = 0
    for i in range(0, n, 3):
        da = aw[i] - bw[i]
        db = aw[i + 1] - bw[i + 1]
        dc = aw[i + 2] - bw[i + 2]
        ad = abs(da) + abs(db) + abs(dc)
        diff_sum += ad
        diff_sq += da * da + db * db + dc * dc
        m = max(abs(da), abs(db), abs(dc))
        if m > max_d:
            max_d = m
        if m > 10:
            bad += 1
    mae = diff_sum / (px * 3)
    rmse = math.sqrt(diff_sq / (px * 3))
    print(f"reference: {a_path} ({a.size[0]}×{a.size[1]})")
    print(f"candidate: {b_path} (resized to reference if needed)")
    print(f"MAE (per channel avg): {mae:.4f}")
    print(f"RMSE (per channel):    {rmse:.4f}")
    print(f"max channel delta:     {max_d}")
    print(f"pixels with |Δ|>10 any ch: {bad} / {px} ({100.0 * bad / px:.2f}%)")


if __name__ == "__main__":
    main()
