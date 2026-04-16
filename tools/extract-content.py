#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def text(self):
        return " ".join(self._chunks)


def rel_to_url(rel_path: Path, host_root: Path, base_url: str) -> str:
    rel = rel_path.relative_to(host_root).as_posix()
    if rel.endswith("index.html"):
        rel = rel[: -len("index.html")]
    if rel.endswith(".html"):
        rel = rel[: -len(".html")]
    rel = rel.lstrip("/")
    if rel:
        return urljoin(base_url, rel)
    return base_url.rstrip("/") + "/"


def parse_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def parse_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return parser.text()


def main():
    parser = argparse.ArgumentParser(description="Extract mirrored HTML content into JSON inventory.")
    parser.add_argument("--mirror-dir", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    mirror_dir = Path(args.mirror_dir).resolve()
    output = Path(args.output).resolve()

    host_dirs = [p for p in mirror_dir.iterdir() if p.is_dir()]
    if not host_dirs:
        raise SystemExit(f"No host directories found under {mirror_dir}")

    host_root = host_dirs[0]
    pages = []

    for html_file in sorted(host_root.rglob("*.html")):
        try:
            html = html_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        url = rel_to_url(html_file, host_root, args.base_url)
        title = parse_title(html)
        text = parse_text(html)

        pages.append(
            {
                "url": url,
                "source_file": str(html_file.relative_to(mirror_dir)),
                "title": title,
                "word_count": len(text.split()),
                "text_preview": text[:500],
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "mirror_dir": str(mirror_dir),
        "page_count": len(pages),
        "pages": pages,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
