"""HTTP probes for citation URLs embedded in markdown (reject 404 / failures)."""

from __future__ import annotations

import ipaddress
import re
import time
from typing import Any, Mapping
from urllib.parse import urlparse

import requests

_WS_TRAIL_RE = re.compile(r"[`\]\)>\s]+$")

# Mirrors kcpest_agent.quality.LINK_RE (duplicate to avoid circular import).
LINK_TOKEN_RE = re.compile(r"https?://[^\s)>\]]+")


def markdown_body_https_urls(markdown_without_frontmatter: str) -> list[str]:
    """Unique http(s) URLs in document order (public hosts only)."""
    raw = LINK_TOKEN_RE.findall(markdown_without_frontmatter)
    out: list[str] = []
    seen: set[str] = set()
    for u in raw:
        u = _cleanup_url_token(u).strip()
        if not _url_is_public_http(u):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _cleanup_url_token(u: str) -> str:
    u = _WS_TRAIL_RE.sub("", u.strip())
    for _ in range(4):
        u2 = u.rstrip(",.;:!?\"'`")
        if u2 == u:
            break
        u = u2
    return u


def _url_is_public_http(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host == "localhost":
        return False
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return False
        return True
    except ValueError:
        pass
    if host.endswith(".local"):
        return False
    return True


def _http_ok(code: int) -> bool:
    return 200 <= code < 400


def _probe_one(session: requests.Session, url: str, timeout: float) -> tuple[bool, str]:
    """HEAD first (cheap); GET streamed if HEAD is unsupported or ambiguous."""
    try:
        h = session.head(url, allow_redirects=True, timeout=timeout)
        if _http_ok(h.status_code):
            return True, ""
        if h.status_code in (404, 410):
            return False, f"HTTP {h.status_code}"
    except requests.Timeout:
        pass
    except requests.RequestException:
        pass

    try:
        g = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
        try:
            sc = g.status_code
            next(g.iter_content(1024), None)
            if _http_ok(sc):
                return True, ""
            if sc in (404, 410):
                return False, f"HTTP {sc}"
            if sc >= 400:
                return False, f"HTTP {sc}"
            return False, f"HTTP {sc}"
        finally:
            g.close()
    except requests.Timeout:
        return False, "timeout"
    except requests.RequestException as exc:
        return False, repr(exc.args[0] if exc.args else exc)


def external_citation_issues(
    markdown_body: str,
    gen_cfg: Mapping[str, Any] | None,
) -> list[str]:
    """
    Human-readable QA issues when citation URLs fail (404/410, timeouts, TLS, etc.).
    Uses ``generation.verify_external_urls`` (default True).
    """
    gen_cfg = gen_cfg or {}
    if not bool(gen_cfg.get("verify_external_urls", True)):
        return []
    timeout = float(gen_cfg.get("url_check_timeout_seconds", 18.0))
    pause = float(gen_cfg.get("url_check_pause_seconds", 0.25))

    urls = markdown_body_https_urls(markdown_body)
    if not urls:
        return []

    print(f"Checking {len(urls)} citation URL(s) over HTTP...")
    session = requests.Session()
    ua = gen_cfg.get("url_check_user_agent")
    session.headers.update(
        {
            "User-Agent": str(
                ua
                or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15 KC-Pest-BlogAgent/1.0",
            ),
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
    )

    issues: list[str] = []
    for u in urls:
        ok, err = _probe_one(session, u, timeout)
        if not ok:
            issues.append(f"Unreachable or bad citation URL (replace this link): {u} ({err})")
        if pause > 0:
            time.sleep(pause)
    return issues
