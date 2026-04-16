#!/usr/bin/env python3
import argparse
import mimetypes
import posixpath
import re
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


class LinkExtractor(HTMLParser):
    ATTRS = {
        "a": "href",
        "link": "href",
        "script": "src",
        "img": "src",
        "source": "src",
    }

    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attr_name = self.ATTRS.get(tag)
        if not attr_name:
            return
        value = dict(attrs).get(attr_name)
        if value:
            self.urls.append(value)


def canonicalize(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    clean = parsed._replace(fragment="", query="", path=path)
    return urlunparse(clean)


def to_local_path(url: str, host_root: Path, content_type: Optional[str]) -> Path:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path.endswith("/"):
        return host_root / path.lstrip("/") / "index.html"

    suffix = Path(path).suffix
    if not suffix and content_type and "text/html" in content_type:
        path = f"{path}.html"
    return host_root / path.lstrip("/")


def is_html(content_type: Optional[str], url: str) -> bool:
    if content_type and "text/html" in content_type:
        return True
    guessed, _ = mimetypes.guess_type(url)
    return guessed == "text/html"


def main():
    parser = argparse.ArgumentParser(description="Simple domain-limited crawler for static migration.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--wait-seconds", type=float, default=0.5)
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args()

    base_url = canonicalize(args.base_url)
    base_host = urlparse(base_url).netloc
    mirror_dir = Path(args.output_dir).resolve()
    host_root = mirror_dir / base_host
    host_root.mkdir(parents=True, exist_ok=True)

    queue = deque([base_url])
    seen_pages = set()
    downloaded_assets = set()
    page_count = 0

    while queue and page_count < args.max_pages:
        url = queue.popleft()
        if url in seen_pages:
            continue
        seen_pages.add(url)

        req = Request(url, headers={"User-Agent": "Mozilla/5.0 kcpest-migration-crawler"})
        try:
            with urlopen(req, timeout=20) as res:
                body = res.read()
                content_type = res.headers.get("Content-Type", "")
        except (HTTPError, URLError, TimeoutError):
            continue

        local_path = to_local_path(url, host_root, content_type)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(body)

        if not is_html(content_type, url):
            downloaded_assets.add(url)
            continue

        page_count += 1
        html = body.decode("utf-8", errors="replace")
        parser = LinkExtractor()
        parser.feed(html)

        for raw_link in parser.urls:
            absolute = canonicalize(urljoin(url, raw_link))
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc != base_host:
                continue

            # Keep pages in queue and eagerly download assets too.
            guessed, _ = mimetypes.guess_type(parsed.path)
            looks_like_asset = guessed is not None and guessed != "text/html"
            if looks_like_asset:
                if absolute in downloaded_assets:
                    continue
                downloaded_assets.add(absolute)
                asset_req = Request(absolute, headers={"User-Agent": "Mozilla/5.0 kcpest-migration-crawler"})
                try:
                    with urlopen(asset_req, timeout=20) as asset_res:
                        asset_body = asset_res.read()
                        asset_type = asset_res.headers.get("Content-Type", "")
                    asset_path = to_local_path(absolute, host_root, asset_type)
                    asset_path.parent.mkdir(parents=True, exist_ok=True)
                    asset_path.write_bytes(asset_body)
                except (HTTPError, URLError, TimeoutError):
                    pass
                continue

            queue.append(absolute)

        time.sleep(args.wait_seconds)

    print(f"Crawled pages: {page_count}")
    print(f"Mirror directory: {mirror_dir}")


if __name__ == "__main__":
    main()
