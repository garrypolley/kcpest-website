from __future__ import annotations

import json
from typing import Any

from kcpest_agent.ollama_client import chat, parse_json_loose


def build_messages(
    *,
    user_prompt: str,
    rag_context: str,
    role: str,
    series_title: str,
    topic_id: str,
    hub_slug: str | None,
    part_number: int,
    prior_posts_summary: str,
) -> list[dict[str, str]]:
    role_hint = (
        "Write the **overview / hub** article: high-level, sets up the week’s theme, and points readers to what we will cover in follow-ups."
        if role == "hub"
        else "Write a **supporting** article: specific subtopic with practical detail that expands on the weekly theme. Assume readers may also read the overview."
    )
    hub_line = (
        f"The series hub slug (for linking) will be `{hub_slug}`."
        if hub_slug
        else "This will become the hub post; use a clear, evergreen title."
    )
    system = f"""You are a senior pest-control educator writing for KC Pest Experts (Kansas City metro: Kansas & Missouri).
{role_hint}

Rules:
- Accurate, practical, non-alarmist. No guaranteed outcomes. No medical advice; suggest consulting professionals for health concerns.
- Use markdown: start body with an intro paragraph, then use ## and ### headings, bullet lists where helpful.
- Include **at least 4** distinct markdown links to authoritative sources (HTTPS) such as CDC, EPA, USDA, or university extension (.edu). Inline citations like [CDC topic](url).
- Add a final ## Sources section listing the same links with one-line descriptions.
- Local angle: mention Kansas City region where natural (outdoor pests, seasonal timing)—avoid fabricating statistics.
- Do NOT include YAML frontmatter in the body; JSON only below.

Context snippets (may be incomplete; verify tone only):
---
{rag_context[:24000]}
---
"""
    user = f"""Weekly theme (series): {series_title}
Topic id: {topic_id}
Part: {part_number} (0 = hub overview)
{hub_line}

User request:
{user_prompt}

Prior posts in this series (titles only):
{prior_posts_summary or "None yet."}

Return **JSON only** with keys:
title (string, <=90 chars),
description (string, 120-200 chars for meta description),
body (string, markdown body without frontmatter).
"""
    if part_number > 0 and hub_slug:
        user += f"""
For this part article, include a brief pointer with a markdown link to the series overview: [series overview](/{hub_slug}).
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_article_json(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    attempt: int,
    feedback: str,
) -> dict[str, Any]:
    extra = ""
    if attempt > 1 and feedback:
        extra = f"\n\nPrevious attempt issues to fix:\n{feedback}\n"
    msgs = messages.copy()
    msgs[-1] = {
        "role": "user",
        "content": msgs[-1]["content"] + extra,
    }
    raw = chat(base_url, model, msgs, temperature=0.35 + min(0.1 * attempt, 0.25), timeout=600)
    try:
        data = parse_json_loose(raw)
    except json.JSONDecodeError:
        # try to extract fenced json
        if "```" in raw:
            chunk = raw.split("```", 2)
            for c in chunk:
                c = c.strip()
                if c.startswith("json"):
                    c = c[4:].strip()
                if c.startswith("{"):
                    data = parse_json_loose(c)
                    break
            else:
                raise
        else:
            raise
    for k in ("title", "description", "body"):
        if k not in data:
            raise ValueError(f"Missing {k} in model output")
    return data


def assemble_markdown(
    *,
    title: str,
    description: str,
    body: str,
    pub_date: str,
    author: str,
    series_topic_id: str,
    series_hub_slug: str,
    series_part: int,
    series_title: str,
    cover_image: str | None = None,
    cover_alt: str | None = None,
) -> str:
    lines = [
        "---",
        f"title: {json.dumps(title)}",
        f"description: {json.dumps(description)}",
        f"pubDate: {pub_date}",
        f"author: {json.dumps(author)}",
    ]
    if cover_image:
        lines.append(f"coverImage: {json.dumps(cover_image)}")
        if cover_alt:
            lines.append(f"coverAlt: {json.dumps(cover_alt)}")
    lines.extend(
        [
            f"seriesTopicId: {json.dumps(series_topic_id)}",
            f"seriesHubSlug: {json.dumps(series_hub_slug)}",
            f"seriesPart: {series_part}",
            f"seriesTitle: {json.dumps(series_title)}",
            "---",
            "",
        ]
    )
    return "\n".join(lines) + body.strip() + "\n"
