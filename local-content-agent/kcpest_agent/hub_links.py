from __future__ import annotations

import re
from pathlib import Path

from kcpest_agent.schedule_public import is_schedule_day_public_central

MARK_BEGIN = "<!-- kcpest-series:begin -->"
MARK_END = "<!-- kcpest-series:end -->"
PART_MARK_BEGIN = "<!-- kcpest-series-footer:begin -->"
PART_MARK_END = "<!-- kcpest-series-footer:end -->"


def blog_post_url(slug: str) -> str:
    """Canonical in-content path for posts (matches /pest-control-blog listing; also available at root /{slug})."""
    s = slug.strip().lstrip("/")
    if not s:
        return "/pest-control-blog/"
    return f"/pest-control-blog/{s}"


def series_entry_line(
    title: str,
    *,
    slug: str | None,
    published_on: str | None,
    current_slug: str | None = None,
) -> str:
    """One series index bullet: this-article, live link, or Coming soon."""
    if slug and current_slug and slug == current_slug:
        return f"- {title} *(this article)*"
    if slug and published_on and is_schedule_day_public_central(published_on):
        return f"- [{title}]({blog_post_url(slug)})"
    return f"- **Coming soon:** {title}"


def render_series_block(
    hub_slug: str,
    series_title: str,
    *,
    siblings: list[tuple[str, str | None, str | None]],  # (title, slug|None, published_on|None)
    current_slug: str,
) -> str:
    hub_url = blog_post_url(hub_slug)
    clean_title = " ".join(series_title.split())
    lines = [
        PART_MARK_BEGIN,
        "## This week’s series",
        "",
        f"This piece is part of our series **{clean_title}**. Start with the [series overview]({hub_url}).",
        "",
    ]
    if len(siblings) > 1:
        lines.append("**Articles in this series:**")
        lines.append("")
        for title, slug, published_on in siblings:
            lines.append(
                series_entry_line(
                    title,
                    slug=slug,
                    published_on=published_on,
                    current_slug=current_slug,
                )
            )
        lines.append("")
    lines.append(PART_MARK_END)
    return "\n".join(lines)


def upsert_hub_series_section(
    hub_path: Path,
    *,
    series_title: str,
    # (title, slug|None, published_on|None) — hub first; None slug => Coming soon
    entries: list[tuple[str, str | None, str | None]],
) -> None:
    text = hub_path.read_text(encoding="utf-8")
    fm_match = re.match(r"^(---\s*\n.*?\n---\s*\n)([\s\S]*)$", text, re.DOTALL)
    if not fm_match:
        raise ValueError("Invalid markdown (frontmatter)")
    fm, body = fm_match.groups()
    clean_title = " ".join(series_title.split())

    block_lines = [
        MARK_BEGIN,
        "## Articles in this series",
        "",
        f"_{clean_title}_",
        "",
    ]
    for title, slug, published_on in entries:
        block_lines.append(
            series_entry_line(title, slug=slug, published_on=published_on)
        )
    block_lines.extend(["", MARK_END, ""])

    block = "\n".join(block_lines)

    if MARK_BEGIN in body and MARK_END in body:
        pattern = re.compile(
            re.escape(MARK_BEGIN) + r"[\s\S]*?" + re.escape(MARK_END),
            re.MULTILINE,
        )
        new_body = pattern.sub(block.strip(), body, count=1)
    else:
        new_body = body.rstrip() + "\n\n" + block + "\n"

    hub_path.write_text(fm + new_body, encoding="utf-8")


def upsert_hub_coming_up_section(
    hub_path: Path,
    *,
    # (label title, slug|None, published_on|None, teaser)
    upcoming: list[tuple[str, str | None, str | None, str]],
) -> None:
    """Rewrite ## Coming up this week bullets to live links or Coming soon."""
    text = hub_path.read_text(encoding="utf-8")
    lines: list[str] = []
    for title, slug, published_on, teaser in upcoming:
        suffix = f" — {teaser}" if teaser.strip() else ""
        if slug and published_on and is_schedule_day_public_central(published_on):
            lines.append(f"- [{title}]({blog_post_url(slug)}){suffix}")
        else:
            lines.append(f"- **Coming soon:** {title}{suffix}")
    section = "## Coming up this week\n\n" + "\n".join(lines) + "\n"

    pattern = re.compile(
        r"## Coming up this week\s*\n(?:[-*].*\n)+",
        re.MULTILINE,
    )
    if pattern.search(text):
        hub_path.write_text(pattern.sub(section + "\n", text, count=1), encoding="utf-8")


def replace_part_series_footer(path: Path, footer_block: str) -> None:
    """Replace an existing series footer (marked or legacy) on a part post."""
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^(---\s*\n.*?\n---\s*\n)([\s\S]*)$", text, re.DOTALL)
    if not fm_match:
        raise ValueError(f"Invalid markdown (frontmatter): {path}")
    fm, body = fm_match.groups()
    block = footer_block.strip() + "\n"

    if PART_MARK_BEGIN in body and PART_MARK_END in body:
        pattern = re.compile(
            re.escape(PART_MARK_BEGIN) + r"[\s\S]*?" + re.escape(PART_MARK_END),
            re.MULTILINE,
        )
        new_body = pattern.sub(block.strip(), body, count=1)
    else:
        # Legacy: strip trailing --- + This week's series section
        legacy = re.compile(
            r"\n---\s*\n+## This week’s series[\s\S]*\Z",
            re.MULTILINE,
        )
        if legacy.search(body):
            new_body = legacy.sub("\n\n---\n\n" + block, body, count=1)
        else:
            new_body = body.rstrip() + "\n\n---\n\n" + block + "\n"

    path.write_text(fm + new_body, encoding="utf-8")


def read_frontmatter_series_title(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^seriesTitle:\s*"((?:\\.|[^"\\])*)"', text, re.MULTILINE)
    if not m:
        m = re.search(r"^seriesTitle:\s*(.+)$", text, re.MULTILINE)
        if not m:
            return None
        raw = m.group(1).strip().strip('"')
    else:
        raw = bytes(m.group(1), "utf-8").decode("unicode_escape")
    clean = " ".join(raw.replace("\\n", " ").split()).strip()
    if not clean:
        return None
    # Reject truncated prompt leftovers
    if "\n" in raw or "Must cite" in clean or clean.lower().startswith("http"):
        return None
    if len(clean) > 120:
        return None
    return clean


def display_series_title(user_prompt: str, hub_path: Path | None = None) -> str:
    """Prefer polished hub seriesTitle; else first line of prompt, capped."""
    if hub_path is not None:
        from_hub = read_frontmatter_series_title(hub_path)
        if from_hub:
            return from_hub
    first = user_prompt.strip().splitlines()[0].strip() if user_prompt.strip() else "Weekly series"
    first = re.sub(r"\s+", " ", first)
    if len(first) > 90:
        first = first[:87].rstrip() + "…"
    return first
