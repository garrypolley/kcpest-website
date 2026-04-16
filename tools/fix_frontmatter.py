#!/usr/bin/env python3
import json
from pathlib import Path


def quote_field(line: str, key: str) -> str:
    prefix = f"{key}: "
    if not line.startswith(prefix):
        return line
    value = line[len(prefix):].rstrip("\n")
    if value.startswith('"') and value.endswith('"'):
        return line
    return f"{prefix}{json.dumps(value)}\n"


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    for idx, line in enumerate(lines):
        if idx == 0 and line.strip() != "---":
            return False
        lines[idx] = quote_field(lines[idx], "title")
        lines[idx] = quote_field(lines[idx], "description")
        lines[idx] = quote_field(lines[idx], "author")
        if lines[idx] != line:
            changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    changed_files = 0
    for folder in (root / "src" / "content" / "pages", root / "src" / "content" / "posts"):
        for file in folder.glob("*.md"):
            if fix_file(file):
                changed_files += 1
    print(f"Frontmatter fixed in {changed_files} files.")


if __name__ == "__main__":
    main()
