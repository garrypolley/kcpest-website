from __future__ import annotations

import argparse
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(
        description="KC Pest local blog agent (Ollama + DuckDuckGo + Astro validation)",
    )
    p.add_argument(
        "command",
        choices=("enqueue", "run-once", "daemon"),
        help="enqueue: save topic; run-once: generate if due; daemon: hourly loop",
    )
    p.add_argument(
        "prompt",
        nargs="*",
        help="Topic text (enqueue only). Example: enqueue Why spring pest control matters now",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate but do not git push or Netlify deploy",
    )
    args = p.parse_args(argv)

    sys.path.insert(0, str(AGENT_ROOT))
    from kcpest_agent.pipeline import daemon, enqueue, run_once

    if args.command == "enqueue":
        text = " ".join(args.prompt).strip()
        if not text:
            p.error("enqueue requires a prompt string")
        enqueue(AGENT_ROOT, text)
        return 0
    if args.command == "run-once":
        return run_once(AGENT_ROOT, dry_run=args.dry_run)
    if args.command == "daemon":
        daemon(AGENT_ROOT, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
