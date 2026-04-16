#!/usr/bin/env python3
import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


PAGE_SLUGS = {
    "": "home",
    "local-pest-control-experts": "local-pest-control-experts",
    "pest-protection-services": "pest-protection-services",
    "bed-bug-service": "bed-bug-service",
    "rodent-pest-control-service": "rodent-pest-control-service",
    "termite-control-service": "termite-control-service",
    "pre-construction-termite-treatments": "pre-construction-termite-treatments",
    "spider-pest-control-service": "spider-pest-control-service",
    "mosquitos-ticks-pest-control": "mosquitos-ticks-pest-control",
    "pest-control-service": "pest-control-service",
    "pest-control-service-areas": "pest-control-service-areas",
    "t/tou-and-privacy": "t-tou-and-privacy",
    "gallery": "gallery",
}


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path


def classify(slug: str) -> str:
    if slug in PAGE_SLUGS:
        return "page"
    if slug == "pest-control-blog":
        return "blog-index"
    return "post"


def sanitize_preview(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    for marker in ("Blog Layout", "REQUEST A SERVICE", "PEST CONTROL SERVICES"):
        if marker in text:
            text = text.split(marker, 1)[-1].strip()
    return text[:500]


def post_frontmatter(title: str, description: str) -> str:
    return (
        "---\n"
        f"title: {title}\n"
        f"description: {description}\n"
        f"pubDate: {date.today().isoformat()}\n"
        "author: KC Pest Experts\n"
        "---\n\n"
    )


def page_frontmatter(title: str, description: str) -> str:
    return (
        "---\n"
        f"title: {title}\n"
        f"description: {description}\n"
        "order: 999\n"
        "---\n\n"
    )


def write_if_missing(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="Import crawled inventory into markdown content files.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    inventory_path = Path(args.inventory).resolve()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    pages_dir = repo_root / "src" / "content" / "pages"
    posts_dir = repo_root / "src" / "content" / "posts"
    mapping_lines = []
    audit_lines = []
    created = 0

    for item in inventory["pages"]:
        source_url = item["url"]
        slug = slug_from_url(source_url)
        category = classify(slug)
        title = item["title"].replace(":", " -").strip() or slug.replace("-", " ").title()
        preview = sanitize_preview(item.get("text_preview", ""))
        description = preview[:155].replace("\n", " ")

        if category == "blog-index":
            mapping_lines.append(f"- `{source_url}` -> `/pest-control-blog` (blog index)")
            audit_lines.append(f"- migrated: `{source_url}` -> `/pest-control-blog`")
            continue

        if category == "page":
            page_slug = PAGE_SLUGS[slug]
            route = "/" if page_slug == "home" else f"/{page_slug}"
            body = f"{page_frontmatter(title, description)}{preview}\n"
            wrote = write_if_missing(pages_dir / f"{page_slug}.md", body, args.overwrite)
            status = "migrated" if wrote or (pages_dir / f"{page_slug}.md").exists() else "needs-manual-edit"
            mapping_lines.append(f"- `{source_url}` -> `{route}`")
            audit_lines.append(f"- {status}: `{source_url}` -> `{route}`")
            created += 1 if wrote else 0
            continue

        post_slug = slug.replace("/", "-")
        route = f"/pest-control-blog/{post_slug}"
        body = (
            f"{post_frontmatter(title, description)}"
            "This entry was imported from the existing site crawl and should be manually polished.\n\n"
            f"{preview}\n"
        )
        wrote = write_if_missing(posts_dir / f"{post_slug}.md", body, args.overwrite)
        status = "migrated" if wrote or (posts_dir / f"{post_slug}.md").exists() else "needs-manual-edit"
        mapping_lines.append(f"- `{source_url}` -> `{route}`")
        audit_lines.append(f"- {status}: `{source_url}` -> `{route}`")
        created += 1 if wrote else 0

    (repo_root / "docs" / "url-mapping.md").write_text(
        "# URL Mapping\n\n" + "\n".join(mapping_lines) + "\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "migration-audit.md").write_text(
        "# Migration Audit\n\n" + "\n".join(audit_lines) + "\n",
        encoding="utf-8",
    )

    print(f"Generated mapping and audit docs. New files written: {created}")


if __name__ == "__main__":
    main()
