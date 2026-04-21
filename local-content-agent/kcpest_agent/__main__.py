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
        choices=("enqueue", "start-week", "backfill-week", "run-once", "daemon"),
        help="start-week / backfill-week: hub+plan; backfill also writes all sub-posts; daemon uses catch-up",
    )
    p.add_argument(
        "prompt",
        nargs="*",
        help="Topic text (enqueue or start-week). Example: start-week Why spring pest control matters now",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate but do not git push or Netlify deploy",
    )
    p.add_argument(
        "--any-time",
        action="store_true",
        help="run-once only: ignore 8am / :13 schedule (for manual testing)",
    )
    p.add_argument(
        "--anchor-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="start-week & backfill-week: hub pubDate and schedule anchor (default for backfill: previous week's Friday in Central Time)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="start-week / backfill-week: replace existing state/weekly_series.json",
    )
    p.add_argument(
        "--only-parts",
        action="store_true",
        help="backfill-week only: do not create hub; generate missing sub-posts 1–3 for existing state",
    )
    args = p.parse_args(argv)

    sys.path.insert(0, str(AGENT_ROOT))
    from kcpest_agent.pipeline import (
        backfill_week,
        daemon,
        enqueue,
        run_once,
        start_week,
    )

    if args.command == "enqueue":
        text = " ".join(args.prompt).strip()
        if not text:
            p.error("enqueue requires a prompt string")
        enqueue(AGENT_ROOT, text)
        return 0
    if args.command == "start-week":
        text = " ".join(args.prompt).strip()
        if not text:
            p.error("start-week requires a prompt string")
        return start_week(
            AGENT_ROOT,
            text,
            dry_run=args.dry_run,
            anchor_iso=args.anchor_date,
            force=args.force,
        )
    if args.command == "backfill-week":
        text = " ".join(args.prompt).strip()
        if not text and not args.only_parts:
            p.error("backfill-week needs a topic string unless you pass --only-parts (existing series)")
        return backfill_week(
            AGENT_ROOT,
            text,
            dry_run=args.dry_run,
            anchor_iso=args.anchor_date,
            only_parts=args.only_parts,
            force=args.force,
        )
    if args.command == "run-once":
        return run_once(
            AGENT_ROOT,
            dry_run=args.dry_run,
            ignore_schedule=args.any_time,
        )
    if args.command == "daemon":
        daemon(AGENT_ROOT, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
