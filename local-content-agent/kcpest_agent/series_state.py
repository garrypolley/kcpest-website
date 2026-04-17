from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
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
class WeeklySeriesState:
    topic_id: str
    week_key: str
    user_prompt: str
    hub_slug: str | None
    posts: list[SeriesPost] = field(default_factory=list)
    created_at: str = ""

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
        )

    def save(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with self.path(state_dir).open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def current_week_key(tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def iso_week_topic_id(user_prompt: str, tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    iso = now.isocalendar()
    base = slugify(user_prompt)[:48].strip("-") or "pest-topic"
    return f"{iso.year}-W{iso.week:02d}-{base}"


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


def already_published_today(state_dir: Path, tz: str) -> bool:
    today = datetime.now(ZoneInfo(tz)).date().isoformat()
    log = load_daily_log(state_dir)
    return log.get("last_publish_date") == today


def record_publish(state_dir: Path, tz: str, slug: str) -> None:
    today = datetime.now(ZoneInfo(tz)).date().isoformat()
    log = load_daily_log(state_dir)
    log["last_publish_date"] = today
    log["last_slug"] = slug
    save_daily_log(state_dir, log)


def before_deadline(cfg: dict[str, Any]) -> bool:
    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")
    hour = int(cfg.get("schedule", {}).get("publish_deadline_hour", 15))
    now = datetime.now(ZoneInfo(tz))
    return now.hour < hour


def today_iso(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).date().isoformat()


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
    )
