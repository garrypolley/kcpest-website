from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from slugify import slugify


@dataclass
class SeriesPost:
    slug: str
    title: str
    published_on: str  # ISO date
    part: int  # 0 = hub
    role: str  # "hub" | "part"


@dataclass
class PlannedSubpost:
    part: int  # 1, 2, 3
    title: str
    focus: str  # one-line angle for generation
    status: str  # "pending" | "published"


@dataclass
class WeeklySeriesState:
    topic_id: str
    week_key: str
    user_prompt: str
    hub_slug: str | None
    posts: list[SeriesPost] = field(default_factory=list)
    created_at: str = ""
    # Anchor calendar day for scheduling parts: hub day = D0; parts at D+1, D+3, D+7
    schedule_anchor_iso: str = ""
    planned: list[PlannedSubpost] = field(default_factory=list)

    @staticmethod
    def path(state_dir: Path) -> Path:
        return state_dir / "weekly_series.json"

    @classmethod
    def load(cls, state_dir: Path) -> WeeklySeriesState | None:
        p = cls.path(state_dir)
        if not p.is_file():
            return None
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        posts = [SeriesPost(**x) for x in raw.get("posts", [])]
        planned_raw = raw.get("planned") or []
        planned = [
            PlannedSubpost(
                part=int(x["part"]),
                title=str(x["title"]),
                focus=str(x.get("focus", "")),
                status=str(x.get("status", "pending")),
            )
            for x in planned_raw
        ]
        tid = raw["topic_id"]
        wk = raw.get("week_key") or ""
        if not wk:
            m = re.match(r"^(\d{4}-W\d{2})", tid)
            wk = m.group(1) if m else ""
        return cls(
            topic_id=tid,
            week_key=wk,
            user_prompt=raw["user_prompt"],
            hub_slug=raw.get("hub_slug"),
            posts=posts,
            created_at=raw.get("created_at", ""),
            schedule_anchor_iso=raw.get("schedule_anchor_iso", ""),
            planned=planned,
        )

    def save(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["planned"] = [asdict(p) for p in self.planned]
        with self.path(state_dir).open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def current_week_key(tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_key_on(day: date, tz: str) -> str:
    z = ZoneInfo(tz)
    dt = datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=z)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def iso_week_topic_id(user_prompt: str, tz: str) -> str:
    return iso_week_topic_id_on_date(user_prompt, datetime.now(ZoneInfo(tz)).date(), tz)


def iso_week_topic_id_on_date(user_prompt: str, on: date, tz: str) -> str:
    z = ZoneInfo(tz)
    dt = datetime(on.year, on.month, on.day, 12, 0, 0, tzinfo=z)
    iso = dt.isocalendar()
    base = slugify(user_prompt)[:48].strip("-") or "pest-topic"
    return f"{iso.year}-W{iso.week:02d}-{base}"


def friday_of_previous_week(tz: str) -> date:
    """Friday that falls in the calendar week *before* the current Monday-start week (America/Chicago)."""
    z = ZoneInfo(tz)
    today = datetime.now(z).date()
    this_monday = today - timedelta(days=today.weekday())  # Monday=0
    return this_monday - timedelta(days=3)  # Friday of previous week


def daily_log_path(state_dir: Path) -> Path:
    return state_dir / "daily_log.json"


def load_daily_log(state_dir: Path) -> dict[str, Any]:
    p = daily_log_path(state_dir)
    if not p.is_file():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_daily_log(state_dir: Path, data: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    with daily_log_path(state_dir).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_publish(state_dir: Path, tz: str, slug: str) -> None:
    today = datetime.now(ZoneInfo(tz)).date().isoformat()
    log = load_daily_log(state_dir)
    log["last_publish_date"] = today
    log["last_slug"] = slug
    save_daily_log(state_dir, log)


def today_iso(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).date().isoformat()


def parse_date_iso(s: str) -> date:
    return date.fromisoformat(s[:10])


def part_due_dates(anchor_iso: str) -> dict[int, str]:
    """Parts 1,2,3 publish on anchor+D+1, D+3, D+7."""
    a = parse_date_iso(anchor_iso)
    return {
        1: (a + timedelta(days=1)).isoformat(),
        2: (a + timedelta(days=3)).isoformat(),
        3: (a + timedelta(days=7)).isoformat(),
    }


def next_due_part(state: WeeklySeriesState, today: str) -> int | None:
    """Next sub-post to publish: earliest part 1–3 that is not published and whose due date is <= today."""
    if not state.schedule_anchor_iso or not state.hub_slug:
        return None
    due = part_due_dates(state.schedule_anchor_iso)
    published_parts = {p.part for p in state.posts if p.part > 0}
    today_d = parse_date_iso(today)
    pending: list[tuple[date, int]] = []
    for part in (1, 2, 3):
        if part in published_parts:
            continue
        d = parse_date_iso(due[part])
        if d <= today_d:
            pending.append((d, part))
    if not pending:
        return None
    pending.sort(key=lambda x: (x[0], x[1]))
    return pending[0][1]


def in_publish_hour(cfg: dict[str, Any], tz: str) -> bool:
    hour = int(cfg.get("schedule", {}).get("publish_hour_central", 8))
    now = datetime.now(ZoneInfo(tz))
    return now.hour == hour


def at_minute_past_hour(cfg: dict[str, Any], tz: str) -> bool:
    minute = int(cfg.get("schedule", {}).get("publish_minute", 13))
    now = datetime.now(ZoneInfo(tz))
    return now.minute == minute


def ensure_series_for_prompt(
    state_dir: Path,
    user_prompt: str,
    tz: str,
) -> WeeklySeriesState:
    wk = current_week_key(tz)
    tid = iso_week_topic_id(user_prompt, tz)
    existing = WeeklySeriesState.load(state_dir)
    if existing and existing.week_key == wk:
        existing.user_prompt = user_prompt
        existing.topic_id = tid
        return existing
    return WeeklySeriesState(
        topic_id=tid,
        week_key=wk,
        user_prompt=user_prompt,
        hub_slug=None,
        posts=[],
        created_at=datetime.now(ZoneInfo(tz)).isoformat(),
        schedule_anchor_iso="",
        planned=[],
    )
