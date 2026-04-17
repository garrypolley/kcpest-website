from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import trafilatura
from duckduckgo_search import DDGS

from kcpest_agent.ollama_client import cosine_sim, embed


@dataclass
class SourceDoc:
    url: str
    title: str
    domain: str
    text: str
    quality_score: float


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def score_url_quality(url: str, trusted: list[str]) -> float:
    d = _domain(url)
    s = 1.0
    for t in trusted:
        if t in d:
            s += 4.0
    if d.endswith(".gov"):
        s += 3.0
    if ".edu" in d:
        s += 2.0
    if "extension" in d:
        s += 1.5
    return s


def _ddg_text_query(query: str, max_per: int) -> list[dict[str, Any]]:
    """Run in a thread so we can enforce a wall-clock timeout (DDGS may hang)."""
    ddgs = DDGS()
    return list(ddgs.text(query, max_results=max_per))


def ddg_search(queries: list[str], max_per: int, *, timeout_s: float = 55.0) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for q in queries:
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_ddg_text_query, q, max_per)
                items = fut.result(timeout=timeout_s)
        except FuturesTimeout:
            continue
        except Exception:
            continue
        for item in items:
            href = item.get("href") or item.get("url") or ""
            if not href or href in seen:
                continue
            seen.add(href)
            results.append(
                {
                    "title": item.get("title") or "",
                    "href": href,
                    "body": item.get("body") or "",
                }
            )
    return results


def fetch_extract(url: str, timeout: int = 25) -> tuple[str, str]:
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=False)
        if not downloaded:
            return "", ""
        meta = trafilatura.extract_metadata(downloaded)
        title = (meta.title if meta else None) or ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return title.strip(), (text or "").strip()
    except Exception:
        return "", ""


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= chunk_chars:
        return [text] if text else []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_chars])
        i += chunk_chars - overlap
    return [c for c in chunks if c.strip()]


def build_rag_context(
    cfg: dict[str, Any],
    topic: str,
    ollama_base: str,
    embed_model: str | None,
) -> tuple[str, list[SourceDoc]]:
    s_cfg = cfg.get("search", {})
    trusted = list(s_cfg.get("trusted_domain_hints", []))
    max_r = int(s_cfg.get("max_results_per_query", 8))
    max_fetch = int(s_cfg.get("max_pages_to_fetch", 6))
    chunk_chars = int(s_cfg.get("chunk_chars", 1200))
    overlap = int(s_cfg.get("chunk_overlap", 200))

    queries = [
        topic,
        f"{topic} site:cdc.gov OR site:epa.gov",
        f"{topic} extension university integrated pest management",
    ]

    ddg_timeout = float(s_cfg.get("ddg_timeout_seconds", 55))
    hits = ddg_search(queries, max_r, timeout_s=ddg_timeout)
    if not hits:
        # Last-resort single query without site: operators (DDGS occasionally stalls on complex queries)
        hits = ddg_search([topic[:200]], min(5, max_r), timeout_s=ddg_timeout)
    docs: list[SourceDoc] = []
    for h in hits:
        url = h["href"]
        q = score_url_quality(url, trusted)
        title_snip = h.get("title", "")
        body_snip = h.get("body", "")
        t_title, t_text = fetch_extract(url)
        combined = "\n".join(
            x for x in (t_title, title_snip, t_text or body_snip) if x
        )
        if len(combined) < 200:
            continue
        docs.append(
            SourceDoc(
                url=url,
                title=t_title or title_snip or url,
                domain=_domain(url),
                text=combined[:50000],
                quality_score=q,
            )
        )
        if len(docs) >= max_fetch * 2:
            break

    docs.sort(key=lambda d: d.quality_score + min(len(d.text), 8000) / 8000, reverse=True)
    docs = docs[:max_fetch]

    topic_keywords = set(re.findall(r"[a-zA-Z]{4,}", topic.lower()))
    chunks_with_scores: list[tuple[float, str, str]] = []

    topic_emb = embed(ollama_base, embed_model, topic, timeout=60) if embed_model else None

    for d in docs:
        for ch in chunk_text(d.text, chunk_chars, overlap):
            kw_score = sum(1 for w in topic_keywords if w in ch.lower()) / max(
                len(topic_keywords), 1
            )
            sim = 0.0
            if topic_emb and embed_model:
                ch_emb = embed(ollama_base, embed_model, ch[:6000], timeout=60)
                if ch_emb:
                    sim = max(0.0, cosine_sim(topic_emb, ch_emb))
            score = d.quality_score * 0.35 + kw_score * 25 + sim * 30
            header = f"[Source: {d.title}]({d.url})"
            chunks_with_scores.append((score, header, ch))

    chunks_with_scores.sort(key=lambda x: x[0], reverse=True)
    top = chunks_with_scores[:12]

    lines: list[str] = []
    for _, header, ch in top:
        lines.append(header)
        lines.append(ch)
        lines.append("")

    return "\n".join(lines), docs
