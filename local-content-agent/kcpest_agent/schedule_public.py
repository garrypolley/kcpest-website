"""Whether a post’s scheduled calendar day is ‘live’ — mirrors site `src/lib/postVisibility.ts` (Central date)."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo


def is_schedule_day_public_central(published_on: str) -> bool:
    """
    ``published_on`` is ``YYYY-MM-DD`` (from front matter or ``SeriesPost.published_on``).
    Public when that calendar day is on or before today in **America/Chicago**.
    """
    v = (os.environ.get("PUBLIC_SHOW_FUTURE_POSTS") or os.environ.get("SHOW_FUTURE_POSTS") or "").lower()
    if v in ("1", "true", "yes"):
        return True
    day = published_on.strip()[:10]
    if len(day) < 10:
        return True
    today = datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    return day <= today
