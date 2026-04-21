from __future__ import annotations

import json
from typing import Any

from kcpest_agent.internal_links import INTERNAL_SERVICE_CTA_BLOCK
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
    prior_content_excerpts: str = "",
    subpost_focus: str = "",
) -> list[dict[str, str]]:
    role_hint = (
        "Write the **overview / hub** article: high-level, sets up the week’s theme, and points readers to what we will cover in follow-ups."
        if role == "hub"
        else (
            "Write a **deep-dive sub-article** for this week’s series only: one focused subtopic with action steps, examples, and clear next steps. "
            "Readers already read the series overview—**do not** re-explain the whole weekly theme or repeat the overview’s structure."
        )
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
{INTERNAL_SERVICE_CTA_BLOCK}
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
"""
    if prior_content_excerpts.strip():
        user += f"""
Excerpts from other posts already published **this same week** (do NOT repeat themes, headings, anecdotes, or phrasing; use different angles, pests, and examples):
---
{prior_content_excerpts[:12000]}
---
"""
    if subpost_focus.strip():
        user += f"""
**This article’s planned focus (stick to this angle):** {subpost_focus}
"""
    if role == "part" and part_number > 0:
        user += """
**Differentiation rules (must follow):**
- Use a **different main title** than the series overview (not a small word change of the same headline).
- Do **not** reuse the overview’s section heading text (e.g. if the hub says “Why Spring…”, do not use that exact phrase as an ## heading).
- At most **one short paragraph** may restate why the weekly theme matters; the rest must be **new** detail: checklists, identification tips, timing, what to ask a pro, or mistakes to avoid for *this* focus only.
- Prefer **different** sources or link targets than the overview when possible; at least two links may mirror the series but the *framing* must be new.
"""
    user += """
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


def build_hub_week_messages(
    *,
    user_prompt: str,
    rag_context: str,
    series_title: str,
    topic_id: str,
    hub_slug: str,
) -> list[dict[str, str]]:
    """Hub post for start-week: editorial trailer + exactly 3 planned sub-article ideas (not the deep dives)."""
    system = f"""You are a senior pest-control marketer and educator for KC Pest Experts (Kansas City metro).

Write the **weekly series hub**—a **short editorial trailer**, not a full deep-dive article.

{INTERNAL_SERVICE_CTA_BLOCK}

**Hub role (critical):**
- This post is the **table of contents + why it matters in 1–2 screens of reading**. The three follow-up posts will carry the heavy how-to and pest-specific detail.
- **Do not** write long “why spring beats summer” essays with the same structure the sub-posts will use. Tease the point in a few paragraphs only; **do not** enumerate every pest category in depth (save termite/ant/rodent specifics for the numbered parts).
- **Do not** use the same main title pattern as the follow-ups will use (avoid a title that could work as Part 1 or 2).
- Include a section **## Coming up this week** with **exactly three** bullets. Each starts with **Coming soon:** then a short label and one sentence on the *unique* angle of that future article (non-overlapping).
- Do not invent URLs for future posts; bullets are plain text only.

**Length target:** body about **350–750 words** (not a 1,200-word pillar page).

Rules:
- Accurate, practical, non-alarmist. No guaranteed outcomes.
- Markdown: intro, ## headings, lists. **At least 4** distinct https:// links (CDC, EPA, extension .edu, etc.) with a final ## Sources section.
- No YAML in body. JSON only below.

Context (may be incomplete):
---
{rag_context[:24000]}
---
"""
    user = f"""Weekly theme (series): {series_title}
Topic id: {topic_id}
Hub slug (for internal reference only; do not link future posts): `{hub_slug}`

User / editor direction:
{user_prompt}

Return **JSON only** with keys:
title (string, <=90 chars),
description (string, 120-200 chars),
body (string, markdown),
planned_subposts (array of **exactly 3** objects, each with keys: title (short working title), focus (one sentence describing the unique angle for that future article — must be **distinct** from each other)).
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_hub_week_json(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    attempt: int,
    feedback: str,
) -> dict[str, Any]:
    """Like generate_article_json but requires planned_subposts (3 distinct angles)."""
    data = generate_article_json(base_url, model, messages, attempt, feedback)
    planned = data.get("planned_subposts")
    if not isinstance(planned, list) or len(planned) != 3:
        raise ValueError("planned_subposts must be a list of exactly 3 objects")
    cleaned: list[dict[str, str]] = []
    for i, item in enumerate(planned):
        if not isinstance(item, dict):
            raise ValueError(f"planned_subposts[{i}] must be an object")
        title = str(item.get("title", "")).strip()
        focus = str(item.get("focus", "")).strip()
        if not title or not focus:
            raise ValueError(f"planned_subposts[{i}] needs non-empty title and focus")
        cleaned.append({"title": title, "focus": focus})
    data["planned_subposts"] = cleaned
    return data


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
