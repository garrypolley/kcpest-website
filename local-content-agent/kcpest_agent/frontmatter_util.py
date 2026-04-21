from __future__ import annotations

import re
from pathlib import Path


def strip_frontmatter(md: str) -> str:
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return md.strip()


def load_post_body(path: Path) -> str:
    return strip_frontmatter(path.read_text(encoding="utf-8"))


def extract_topic_id(md_text: str) -> str | None:
    m = re.search(r"^seriesTopicId:\s*(.+)$", md_text, re.MULTILINE)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.startswith('"'):
        return raw.strip('"')[:500]
    return raw[:500]
