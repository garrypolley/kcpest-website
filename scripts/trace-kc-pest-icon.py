#!/usr/bin/env python3
"""
Trace kc-pest-lockup-official.png icon into SVG paths (color layers + holes).
Usage: python3 scripts/trace-kc-pest-icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "public/images/brand/kc-pest-lockup-official.png"
ICON_RIGHT = 46


def contour_to_path(cnt: np.ndarray, epsilon: float) -> str:
    cnt = cv2.approxPolyDP(cnt, epsilon, True)
    if len(cnt) < 3:
        return ""
    pts = cnt.reshape(-1, 2).astype(float)
    x0, y0 = pts[0]
    parts = [f"M{x0:.2f} {y0:.2f}"]
    for x, y in pts[1:]:
        parts.append(f"L{x:.2f} {y:.2f}")
    parts.append("Z")
    return "".join(parts)


def compound_path(contours: list, eps: float) -> str:
    bits: list[str] = []
    for cnt in contours:
        p = contour_to_path(cnt, eps)
        if p:
            bits.append(p)
    return " ".join(bits)


def main() -> None:
    bgra = cv2.imread(str(SRC), cv2.IMREAD_UNCHANGED)
    if bgra is None:
        print("Missing", SRC, file=sys.stderr)
        sys.exit(1)
    bgr = bgra[:, :, :3]
    alpha = bgra[:, :, 3] if bgra.shape[2] == 4 else np.full(bgr.shape[:2], 255, dtype=np.uint8)
    icon = bgr[:, :ICON_RIGHT].copy()
    aicon = alpha[:, :ICON_RIGHT]
    white = np.ones_like(icon) * 255
    a3 = (aicon.astype(np.float32) / 255.0)[:, :, None]
    comp = (icon.astype(np.float32) * a3 + white.astype(np.float32) * (1 - a3)).astype(np.uint8)

    flat = comp.reshape(-1, 3).astype(np.float32)
    med = np.array([188, 136, 44], dtype=np.float32)
    dark = np.array([128, 60, 32], dtype=np.float32)
    d_med = np.linalg.norm(flat - med, axis=1)
    d_dark = np.linalg.norm(flat - dark, axis=1)
    thresh = 48.0
    med_mask = ((d_med < thresh) & (d_med <= d_dark)).reshape(comp.shape[:2]).astype(np.uint8) * 255
    dark_mask = ((d_dark < thresh) & (d_dark < d_med)).reshape(comp.shape[:2]).astype(np.uint8) * 255
    k = np.ones((3, 3), np.uint8)
    med_mask = cv2.morphologyEx(med_mask, cv2.MORPH_CLOSE, k)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, k)

    med_hex = "#2c89c9"
    dark_hex = "#213d81"

    print(f"<!-- source: {SRC.name}, icon x∈[0,{ICON_RIGHT}) -->")

    cnts_m, _ = cv2.findContours(med_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts_m = sorted(cnts_m, key=cv2.contourArea, reverse=True)
    if cnts_m and cv2.contourArea(cnts_m[0]) > 10:
        d = contour_to_path(cnts_m[0], 1.0)
        print(f'<path class="logo-fill" fill="{med_hex}" d="{d}"/>')

    cnts_d, _ = cv2.findContours(dark_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if len(cnts_d) > 0:
        dcompound = compound_path(cnts_d, 0.75)
        print(
            f'<path class="logo-stroke" fill="{dark_hex}" fill-rule="evenodd" d="{dcompound}"/>'
        )


if __name__ == "__main__":
    main()
