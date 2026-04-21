from __future__ import annotations

import re
from pathlib import Path

from kcpest_agent.schedule_public import is_schedule_day_public_central

MARK_BEGIN = "<!-- kcpest-series:begin -->"
MARK_END = "<!-- kcpest-series:end -->"


def render_series_block(
    hub_slug: str,
    series_title: str,
    *,
    siblings: list[tuple[str, str, str]],  # (title, slug, published_on YYYY-MM-DD)
    current_slug: str,
) -> str:
    hub_url = f"/{hub_slug}"
    lines = [
        "## This week’s series",
        "",
        f"This piece is part of our series **{series_title}**. Start with the [series overview]({hub_url}).",
        "",
    ]
    if len(siblings) > 1:
        lines.append("**Articles in this series:**")
        lines.append("")
        for title, slug, published_on in siblings:
            if slug == current_slug:
                lines.append(f"- {title} *(this article)*")
            elif is_schedule_day_public_central(published_on):
                lines.append(f"- [{title}](/{slug})")
            else:
                lines.append(f"- **Coming soon:** {title}")
        lines.append("")
    return "\n".join(lines)


def upsert_hub_series_section(
    hub_path: Path,
    *,
    series_title: str,
    # (title, slug, published_on YYYY-MM-DD) — hub first; use same Central-day rule as the live site
    entries: list[tuple[str, str, str]],
) -> None:
    text = hub_path.read_text(encoding="utf-8")
    fm_match = re.match(r"^(---\s*\n.*?\n---\s*\n)([\s\S]*)$", text, re.DOTALL)
    if not fm_match:
        raise ValueError("Invalid markdown (frontmatter)")
    fm, body = fm_match.groups()

    block_lines = [
        MARK_BEGIN,
        "## Articles in this series",
        "",
        f"_{series_title}_",
        "",
    ]
    for title, slug, published_on in entries:
        if is_schedule_day_public_central(published_on):
            block_lines.append(f"- [{title}](/{slug})")
        else:
            block_lines.append(f"- **Coming soon:** {title}")
    block_lines.extend(["", MARK_END, ""])

    block = "\n".join(block_lines)

    if MARK_BEGIN in body and MARK_END in body:
        pattern = re.compile(
            re.escape(MARK_BEGIN) + r"[\s\S]*?" + re.escape(MARK_END),
            re.MULTILINE,
        )
        new_body = pattern.sub(block.strip(), body, count=1)
    else:
        # Place the series index after the article body for natural reading order
        new_body = body.rstrip() + "\n\n" + block + "\n"

    hub_path.write_text(fm + new_body, encoding="utf-8")
