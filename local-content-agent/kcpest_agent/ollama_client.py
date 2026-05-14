from __future__ import annotations

import json
import re
from typing import Any

import requests


def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    format_json: bool = False,
    timeout: int = 600,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if format_json:
        payload["format"] = "json"
    try:
        r = requests.post(
            f"{base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
    except requests.exceptions.HTTPError:
        if format_json:
            del payload["format"]
            r = requests.post(
                f"{base_url.rstrip('/')}/api/chat",
                json=payload,
                timeout=timeout,
            )
            r.raise_for_status()
        else:
            raise
    data = r.json()
    return data.get("message", {}).get("content", "").strip()


def embed(base_url: str, model: str, text: str, timeout: int = 120) -> list[float] | None:
    try:
        r = requests.post(
            f"{base_url.rstrip('/')}/api/embeddings",
            json={"model": model, "prompt": text[:8000]},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        emb = data.get("embedding")
        if isinstance(emb, list):
            return [float(x) for x in emb]
    except Exception:
        return None
    return None


def cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


def repair_json_control_chars_in_strings(s: str) -> str:
    """Escape raw newlines / strip ASCII controls inside JSON string literals so ``json.loads`` works."""
    out: list[str] = []
    i = 0
    in_str = False
    escape = False
    while i < len(s):
        ch = s[i]
        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            i += 1
            continue
        if in_str:
            if ch == "\r":
                out.append("\\n")
                if i + 1 < len(s) and s[i + 1] == "\n":
                    i += 2
                else:
                    i += 1
                continue
            if ch == "\n":
                out.append("\\n")
                i += 1
                continue
            if ord(ch) < 32 and ch != "\t":
                out.append(" ")
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    candidates = [text, repair_json_control_chars_in_strings(text)]
    last_err: json.JSONDecodeError | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    raise json.JSONDecodeError("empty JSON candidate", text, 0)
