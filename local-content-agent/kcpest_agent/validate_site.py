from __future__ import annotations

import subprocess
from pathlib import Path


def run_npm_build(project_root: Path, timeout: int = 300) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            ["npm", "run", "build"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        ok = p.returncode == 0
        tail = (p.stdout + "\n" + p.stderr)[-6000:]
        return ok, tail
    except Exception as exc:
        return False, str(exc)
