from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from kcpest_agent.ollama_client import chat, parse_json_loose


FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL | re.MULTILINE)
LINK_RE = re.compile(r"https?://[^\s)>\]]+")


def parse_frontmatter(md: str) -> dict[str, str]:
    m = FRONT_MATTER_RE.match(md)
    if not m:
        return {}
    block = m.group(1)
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def word_count_body(md: str) -> int:
    body = FRONT_MATTER_RE.sub("", md, count=1)
    words = re.findall(r"[A-Za-z0-9']+", body)
    return len(words)


def count_external_links(md: str) -> int:
    body = FRONT_MATTER_RE.sub("", md, count=1)
    return len(LINK_RE.findall(body))


def heuristic_score(
    md: str,
    *,
    min_words: int,
    min_links: int,
    build_ok: bool,
) -> tuple[float, list[str]]:
    issues: list[str] = []
    score = 0.0
    fm = parse_frontmatter(md)
    if build_ok:
        score += 40
    else:
        issues.append("Astro build failed")

    required = ["title", "description", "pubDate"]
    missing = [k for k in required if not fm.get(k)]
    if not missing:
        score += 15
    else:
        issues.append(f"Frontmatter missing: {missing}")

    wc = word_count_body(md)
    if wc >= min_words:
        score += 10
    else:
        issues.append(f"Word count {wc} < {min_words}")

    nlinks = count_external_links(md)
    if nlinks >= min_links:
        score += 15
    else:
        issues.append(f"External links {nlinks} < {min_links}")

    desc = fm.get("description", "")
    if 40 <= len(desc) <= 220:
        score += 10
    else:
        issues.append("Description length should be ~40–220 chars")

    title = fm.get("title", "")
    if 20 <= len(title) <= 100:
        score += 10
    else:
        issues.append("Title length unusual")

    # Structure: at least two ## sections in body
    body = FRONT_MATTER_RE.sub("", md, count=1)
    h2 = len(re.findall(r"(?m)^##\s+\S", body))
    if h2 >= 2:
        score += 10
    else:
        issues.append("Need at least two ## sections in body")

    return min(100.0, score), issues


def llm_quality_score(
    base_url: str,
    model: str,
    article_markdown: str,
) -> tuple[float, str]:
    body = FRONT_MATTER_RE.sub("", article_markdown, count=1)[:12000]
    messages = [
        {
            "role": "system",
            "content": (
                "You evaluate pest-control educational blog drafts for accuracy tone, structure, "
                "and appropriate caution (no exaggerated medical claims). "
                "Reply with JSON only: {\"score\": number 0-100, \"notes\": string}."
            ),
        },
        {
            "role": "user",
            "content": f"Evaluate this article body (markdown):\n\n{body}",
        },
    ]
    try:
        raw = chat(base_url, model, messages, temperature=0.1, format_json=True, timeout=120)
        data = parse_json_loose(raw)
        s = float(data.get("score", 0))
        notes = str(data.get("notes", ""))
        return max(0.0, min(100.0, s)), notes
    except Exception as exc:
        return 75.0, f"LLM scorer unavailable ({exc}); using neutral default"


def combined_score(heuristic: float, llm: float, llm_used: bool) -> float:
    if llm_used:
        return round(heuristic * 0.55 + llm * 0.45, 2)
    return round(heuristic * 1.05, 2)  # slight boost if no LLM judge


def passes_threshold(combined: float, threshold: float) -> bool:
    return combined >= threshold
