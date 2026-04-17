#!/usr/bin/env python3
"""
Analyze kc-pest-lockup-official.png icon column and print reference geometry
for hand-authored SVG (hex hull, medium-blue regions inside eroded hex).

Does not auto-generate the full logo; legs remain stroked paths in SiteLogo.astro.

Requires: pip install opencv-python-headless numpy pillow
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "public/images/brand/kc-pest-lockup-official.png"
ICON_W = 46


def main() -> None:
    bgra = cv2.imread(str(SRC), cv2.IMREAD_UNCHANGED)
    if bgra is None:
        print("Missing", SRC, file=sys.stderr)
        sys.exit(1)
    icon = bgra[:, :ICON_W]
    bgr = icon[:, :, :3]
    a = icon[:, :, 3]
    white = np.ones_like(bgr) * 255
    a3 = (a.astype(np.float32) / 255.0)[:, :, None]
    comp = (bgr.astype(np.float32) * a3 + white.astype(np.float32) * (1 - a3)).astype(np.uint8)
    flat = comp.reshape(-1, 3).astype(np.float32)
    med = np.array([188, 136, 44], dtype=np.float32)
    dark = np.array([128, 60, 32], dtype=np.float32)
    d_med = np.linalg.norm(flat - med, axis=1).reshape(comp.shape[:2])
    d_dark = np.linalg.norm(flat - dark, axis=1).reshape(comp.shape[:2])
    med_m = ((d_med < 45) & (d_med <= d_dark)).astype(np.uint8) * 255

    gray = cv2.cvtColor(comp, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnt = max(cnts, key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    eps = 0.02 * cv2.arcLength(hull, True)
    hexv = cv2.approxPolyDP(hull, eps, True).reshape(-1, 2)

    print("Hex hull vertices (lockup icon, convex):")
    for x, y in hexv:
        print(f"  {int(x)},{int(y)}")

    hull_pts = hexv.astype(np.int32)
    mask = np.zeros(comp.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, hull_pts, 255)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.erode(mask, kernel, iterations=2)
    med_m = cv2.bitwise_and(med_m, med_m, mask=mask)
    cnts2, _ = cv2.findContours(med_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print("\nMedium-blue regions (simplified):")
    for c in sorted(cnts2, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < 5:
            continue
        ap = cv2.approxPolyDP(c, 1.0, True)
        pts = ap.reshape(-1, 2)
        d = "M" + " L".join(f"{p[0]:.0f},{p[1]:.0f}" for p in pts) + "Z"
        print(f"  area≈{cv2.contourArea(c):.0f}  {d}")


if __name__ == "__main__":
    main()
