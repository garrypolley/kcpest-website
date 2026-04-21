"""Lightweight text overlap checks vs prior posts in the same series week."""

from __future__ import annotations

import re
from pathlib import Path


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{4,}", text.lower()))


def jaccard_similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    union = len(wa | wb)
    return inter / union if union else 0.0


def overlap_with_any(new_body: str, prior_bodies: list[str], threshold: float = 0.22) -> tuple[bool, str]:
    """Return (too_similar, reason) if any prior exceeds threshold."""
    for i, prev in enumerate(prior_bodies):
        sim = jaccard_similarity(new_body, prev)
        if sim >= threshold:
            return True, f"High word-overlap (~{sim:.0%}) vs prior post #{i+1}; rewrite with new angles and examples."
    return False, ""
