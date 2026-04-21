from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from slugify import slugify

from kcpest_agent.config import load_config, project_root
from kcpest_agent.content_dedup import overlap_with_any
from kcpest_agent.frontmatter_util import load_post_body
from kcpest_agent.generate import (
    assemble_markdown,
    build_hub_week_messages,
    build_messages,
    generate_article_json,
    generate_hub_week_json,
)
from kcpest_agent.hub_links import render_series_block, upsert_hub_series_section
from kcpest_agent.quality import (
    combined_score,
    heuristic_score,
    llm_quality_score,
    passes_threshold,
    word_count_body,
)
from kcpest_agent.search_rag import build_rag_context
from kcpest_agent.series_state import (
    PlannedSubpost,
    SeriesPost,
    WeeklySeriesState,
    friday_of_previous_week,
    in_publish_hour,
    at_minute_past_hour,
    iso_week_topic_id_on_date,
    next_due_part,
    part_due_dates,
    record_publish,
    today_iso,
    week_key_on,
)
from kcpest_agent.validate_site import run_npm_build


def unique_slug(base: str, posts_dir: Path) -> str:
    s = slugify(base)[:72] or "pest-article"
    candidate = s
    n = 2
    while (posts_dir / f"{candidate}.md").exists():
        candidate = f"{s}-{n}"
        n += 1
    return candidate


def append_series_footer(
    body: str,
    *,
    hub_slug: str,
    series_title: str,
    current_slug: str,
    siblings: list[tuple[str, str, str]],  # title, slug, published_on (YYYY-MM-DD)
) -> str:
    block = render_series_block(
        hub_slug,
        series_title,
        siblings=siblings,
        current_slug=current_slug,
    )
    return body.rstrip() + "\n\n---\n\n" + block + "\n"


def publish_git(
    project_root: Path,
    paths: list[Path],
    message: str,
    *,
    do_commit: bool,
    do_push: bool,
) -> None:
    if not do_commit:
        print("Git commit skipped (publish.git_commit=false).")
        return
    rel = [str(p.relative_to(project_root)) for p in paths]
    subprocess.run(["git", "add", *rel], cwd=project_root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=project_root, check=True)
    if do_push:
        subprocess.run(["git", "push", "origin", "main"], cwd=project_root, check=True)


def publish_netlify(project_root: Path, *, enabled: bool, prod: bool) -> None:
    if not enabled:
        print("Netlify deploy skipped.")
        return
    cmd = ["netlify", "deploy"]
    if prod:
        cmd.append("--prod")
    subprocess.run(cmd, cwd=project_root, check=True)


def sleep_until_minute_past_hour(tzname: str, minute_mark: int) -> None:
    """Sleep until the next local clock time at :minute_mark:00 (used for :13 ticks)."""
    z = ZoneInfo(tzname)
    now = datetime.now(z)
    carry = now.replace(second=0, microsecond=0)
    if carry.minute < minute_mark:
        target = carry.replace(minute=minute_mark)
    elif carry.minute > minute_mark or (carry.minute == minute_mark and now.second > 0):
        target = (carry + timedelta(hours=1)).replace(
            minute=minute_mark, second=0, microsecond=0
        )
    else:
        target = carry
    delay = (target - now).total_seconds()
    if delay > 0:
        time.sleep(delay)


def priors_excerpt_block(posts_dir: Path, series: WeeklySeriesState) -> str:
    ordered = sorted(series.posts, key=lambda x: (x.part, x.published_on))
    parts: list[str] = []
    for sp in ordered:
        path = posts_dir / f"{sp.slug}.md"
        if not path.is_file():
            continue
        body = load_post_body(path)
        flat = re.sub(r"\s+", " ", body).strip()[:2000]
        parts.append(f"### Prior: {sp.title}\n{flat}")
    return "\n\n".join(parts)


def start_week(
    agent_root: Path,
    user_prompt: str,
    *,
    dry_run: bool = False,
    anchor_iso: str | None = None,
    force: bool = False,
) -> int:
    """Create the weekly hub + 3 planned sub-angles. ``anchor_iso`` = hub ``pubDate`` (YYYY-MM-DD), default today."""
    cfg = load_config(agent_root)
    if dry_run:
        cfg.setdefault("publish", {})
        cfg["publish"]["enabled"] = False
        cfg["publish"]["git_commit"] = False
        cfg["publish"]["git_push"] = False
        cfg["publish"]["netlify_deploy"] = False

    root = project_root(cfg, agent_root)
    state_dir = agent_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    posts_dir = root / "src" / "content" / "posts"
    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")
    if force and WeeklySeriesState.path(state_dir).is_file():
        WeeklySeriesState.path(state_dir).unlink()

    if not user_prompt.strip():
        print("Empty prompt.", file=sys.stderr)
        return 1

    anchor = (anchor_iso or today_iso(tz))[:10]
    anchor_d = date.fromisoformat(anchor)
    wk = week_key_on(anchor_d, tz)

    existing = WeeklySeriesState.load(state_dir)
    if not force and (
        existing
        and existing.week_key == wk
        and existing.hub_slug
        and any(p.part == 0 for p in existing.posts)
    ):
        print(
            "This series week already has a hub. Use --force or remove state/weekly_series.json.",
            file=sys.stderr,
        )
        return 1

    topic_id = iso_week_topic_id_on_date(user_prompt, anchor_d, tz)
    hub_slug = unique_slug(f"series-overview-{topic_id}", posts_dir)
    series_title = user_prompt.strip()[:160]

    ollama = cfg.get("ollama", {})
    base_url = ollama.get("base_url", "http://127.0.0.1:11434")
    chat_model = ollama.get("chat_model", "llama3.2")
    embed_model = ollama.get("embed_model") or None

    gen_cfg = cfg.get("generation", {})
    max_attempts = int(gen_cfg.get("max_attempts", 20))
    min_q = float(gen_cfg.get("min_quality_score", 90))
    min_words = int(gen_cfg.get("min_words", 500))
    hub_min_words = int(gen_cfg.get("hub_min_words", 360))
    hub_max_words = int(gen_cfg.get("hub_max_words", 900))
    min_links = int(gen_cfg.get("min_external_citation_links", 3))
    print("Building RAG context...")
    rag_text, _docs = build_rag_context(cfg, user_prompt, base_url, embed_model)

    feedback = ""
    best_score = -1.0

    for attempt in range(1, max_attempts + 1):
        print(f"Hub generation attempt {attempt}/{max_attempts}...")
        messages = build_hub_week_messages(
            user_prompt=user_prompt,
            rag_context=rag_text,
            series_title=series_title,
            topic_id=topic_id,
            hub_slug=hub_slug,
        )
        try:
            data = generate_hub_week_json(base_url, chat_model, messages, attempt, feedback)
        except Exception as exc:
            feedback = f"Model output invalid: {exc}"
            print(feedback)
            time.sleep(2)
            continue

        title = str(data["title"]).strip()
        description = str(data["description"]).strip()
        body = str(data["body"]).strip()
        planned_raw = data["planned_subposts"]

        slug = hub_slug
        raw_cover = cfg.get("default_cover_image")
        if raw_cover is None or str(raw_cover).strip() == "":
            cover: str | None = None
            cover_alt: str | None = None
        else:
            cover = str(raw_cover).strip()
            cover_alt = title[:120]

        md = assemble_markdown(
            title=title,
            description=description,
            body=body,
            pub_date=anchor,
            author="KC Pest Experts",
            series_topic_id=topic_id,
            series_hub_slug=hub_slug,
            series_part=0,
            series_title=series_title,
            cover_image=cover,
            cover_alt=cover_alt,
        )
        out_path = posts_dir / f"{slug}.md"
        out_path.write_text(md, encoding="utf-8")

        upsert_hub_series_section(
            out_path,
            series_title=series_title,
            entries=[(title, slug, anchor)],
        )

        build_ok, build_log = run_npm_build(root)
        if not build_ok:
            feedback = f"Astro build failed:\n{build_log[-2000:]}"
            print(feedback)
            out_path.unlink(missing_ok=True)
            time.sleep(2)
            continue

        md_read = out_path.read_text(encoding="utf-8")
        wc_hub = word_count_body(md_read)
        if wc_hub > hub_max_words:
            feedback = (
                f"Hub body is {wc_hub} words; shorten to a trailer under ~{hub_max_words} words "
                "(no pillar-page length)."
            )
            print(feedback)
            out_path.unlink(missing_ok=True)
            time.sleep(2)
            continue

        h_score, h_issues = heuristic_score(
            md_read,
            min_words=hub_min_words,
            min_links=min_links,
            build_ok=True,
        )
        llm_s, llm_notes = llm_quality_score(base_url, chat_model, md_read)
        overall = combined_score(h_score, llm_s, True)
        print(f"Heuristic: {h_score:.1f} LLM: {llm_s:.1f} Combined: {overall:.1f}")
        if h_issues:
            print("Heuristic issues:", "; ".join(h_issues))
        print("LLM notes:", llm_notes[:400])

        if overall > best_score:
            best_score = overall

        if passes_threshold(overall, min_q) and h_score >= 82:
            planned_objs = [
                PlannedSubpost(
                    part=i + 1,
                    title=planned_raw[i]["title"],
                    focus=planned_raw[i]["focus"],
                    status="pending",
                )
                for i in range(3)
            ]
            series = WeeklySeriesState(
                topic_id=topic_id,
                week_key=wk,
                user_prompt=user_prompt.strip(),
                hub_slug=slug,
                posts=[
                    SeriesPost(
                        slug=slug,
                        title=title,
                        published_on=anchor,
                        part=0,
                        role="hub",
                    )
                ],
                created_at=datetime.now(ZoneInfo(tz)).isoformat(),
                schedule_anchor_iso=anchor,
                planned=planned_objs,
            )
            series.save(state_dir)

            pub = cfg.get("publish", {})
            if pub.get("enabled") and pub.get("git_commit", True):
                try:
                    publish_git(
                        root,
                        [out_path],
                        f"Blog (weekly hub): {title[:60]}",
                        do_commit=True,
                        do_push=bool(pub.get("git_push", True)),
                    )
                    if pub.get("netlify_deploy", False):
                        publish_netlify(root, enabled=True, prod=bool(pub.get("netlify_prod", True)))
                except subprocess.CalledProcessError as exc:
                    print("Git/netlify failed:", exc)
                    out_path.unlink(missing_ok=True)
                    return 1
            else:
                print("Skipping git push (publish disabled or dry run).")

            record_publish(state_dir, tz, slug)
            print("Weekly hub ready:", slug, "combined score:", overall)
            print(
                "Sub-posts scheduled for anchor +1, +3, +7 days;",
                "daemon publishes at 8:00 (America/Chicago) on the :13 tick.",
            )
            return 0

        feedback = "; ".join(h_issues) + " | " + llm_notes
        out_path.unlink(missing_ok=True)
        print(f"Below threshold ({min_q}). Retrying...")

    print("Failed after max attempts. Best combined score:", best_score)
    return 1


def _try_publish_subpost(
    agent_root: Path,
    *,
    dry_run: bool,
    part_num: int,
    pub_date: str,
) -> int:
    """Write one part (1–3) with ``pubDate`` = scheduled calendar day. Returns 0 on success."""
    cfg = load_config(agent_root)
    if dry_run:
        cfg.setdefault("publish", {})
        cfg["publish"]["enabled"] = False
        cfg["publish"]["git_commit"] = False
        cfg["publish"]["git_push"] = False
        cfg["publish"]["netlify_deploy"] = False

    root = project_root(cfg, agent_root)
    state_dir = agent_root / "state"
    posts_dir = root / "src" / "content" / "posts"
    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")
    series = WeeklySeriesState.load(state_dir)
    if not series or not series.hub_slug or not series.schedule_anchor_iso:
        return 1

    planned = next((p for p in series.planned if p.part == part_num), None)
    sub_focus = planned.focus if planned else ""
    sub_title_hint = planned.title if planned else ""

    ollama = cfg.get("ollama", {})
    base_url = ollama.get("base_url", "http://127.0.0.1:11434")
    chat_model = ollama.get("chat_model", "llama3.2")
    embed_model = ollama.get("embed_model") or None

    gen_cfg = cfg.get("generation", {})
    max_attempts = int(gen_cfg.get("max_attempts", 20))
    min_q = float(gen_cfg.get("min_quality_score", 90))
    min_words = int(gen_cfg.get("min_words", 500))
    min_links = int(gen_cfg.get("min_external_citation_links", 3))
    overlap_thr = float(gen_cfg.get("max_word_overlap_vs_series", 0.22))
    # Part 1 is only compared to the hub so far — shared topic words are expected; allow a looser ceiling.
    th_use = (
        float(gen_cfg.get("max_word_overlap_part1_vs_series", 0.26))
        if part_num == 1
        else overlap_thr
    )

    hub_slug = series.hub_slug
    series_title = series.user_prompt.strip()[:160]
    user_prompt = series.user_prompt

    prior_slugs = [p.slug for p in sorted(series.posts, key=lambda x: (x.part, x.published_on))]
    prior_bodies = []
    for s in prior_slugs:
        pp = posts_dir / f"{s}.md"
        if pp.is_file():
            prior_bodies.append(load_post_body(pp))

    prior_summary = "\n".join(f"- {p.title}" for p in sorted(series.posts, key=lambda x: x.published_on))
    excerpt_block = priors_excerpt_block(posts_dir, series)

    print("Building RAG context for sub-post...")
    rag_text, _docs = build_rag_context(cfg, user_prompt, base_url, embed_model)

    feedback = ""
    best_score = -1.0

    for attempt in range(1, max_attempts + 1):
        print(f"Sub-post part {part_num} attempt {attempt}/{max_attempts}...")
        messages = build_messages(
            user_prompt=user_prompt,
            rag_context=rag_text,
            role="part",
            series_title=series_title,
            topic_id=series.topic_id,
            hub_slug=hub_slug,
            part_number=part_num,
            prior_posts_summary=prior_summary,
            prior_content_excerpts=excerpt_block,
            subpost_focus=(sub_focus + (f" (working title: {sub_title_hint})" if sub_title_hint else "")),
        )
        try:
            data = generate_article_json(base_url, chat_model, messages, attempt, feedback)
        except Exception as exc:
            feedback = f"Model output invalid: {exc}"
            print(feedback)
            time.sleep(2)
            continue

        title = str(data["title"]).strip()
        description = str(data["description"]).strip()
        body = str(data["body"]).strip()

        too_close, reason = overlap_with_any(body, prior_bodies, threshold=th_use)
        if too_close:
            feedback = reason
            print("Dedup:", reason)
            time.sleep(2)
            continue

        slug = unique_slug(title, posts_dir)

        hub_p = next((p for p in series.posts if p.part == 0), None)
        if not hub_p:
            feedback = "Internal state error: hub missing"
            continue
        sibs: list[tuple[str, str, str]] = [
            (hub_p.title, hub_p.slug, hub_p.published_on),
        ]
        for p in sorted([x for x in series.posts if x.part > 0], key=lambda x: x.published_on):
            sibs.append((p.title, p.slug, p.published_on))
        sibs.append((title, slug, pub_date))
        body_final = append_series_footer(
            body,
            hub_slug=hub_p.slug,
            series_title=series_title,
            current_slug=slug,
            siblings=sibs,
        )

        raw_cover = cfg.get("default_cover_image")
        if raw_cover is None or str(raw_cover).strip() == "":
            cover: str | None = None
            cover_alt: str | None = None
        else:
            cover = str(raw_cover).strip()
            cover_alt = title[:120]

        md = assemble_markdown(
            title=title,
            description=description,
            body=body_final,
            pub_date=pub_date,
            author="KC Pest Experts",
            series_topic_id=series.topic_id,
            series_hub_slug=hub_slug,
            series_part=part_num,
            series_title=series_title,
            cover_image=cover,
            cover_alt=cover_alt,
        )

        out_path = posts_dir / f"{slug}.md"
        out_path.write_text(md, encoding="utf-8")

        build_ok, build_log = run_npm_build(root)
        if not build_ok:
            feedback = f"Astro build failed:\n{build_log[-2000:]}"
            print(feedback)
            out_path.unlink(missing_ok=True)
            time.sleep(2)
            continue

        md_read = out_path.read_text(encoding="utf-8")
        h_score, h_issues = heuristic_score(
            md_read,
            min_words=min_words,
            min_links=min_links,
            build_ok=True,
        )
        llm_s, llm_notes = llm_quality_score(base_url, chat_model, md_read)
        overall = combined_score(h_score, llm_s, True)
        print(f"Heuristic: {h_score:.1f} LLM: {llm_s:.1f} Combined: {overall:.1f}")
        if h_issues:
            print("Heuristic issues:", "; ".join(h_issues))
        print("LLM notes:", llm_notes[:400])

        if overall > best_score:
            best_score = overall

        if passes_threshold(overall, min_q) and h_score >= 82:
            hub_path = posts_dir / f"{hub_slug}.md"
            if hub_path.is_file():
                hub_row = next(p for p in series.posts if p.part == 0)
                rows: list[tuple[str, str, str]] = [
                    (hub_row.title, hub_row.slug, hub_row.published_on),
                ]
                for p in sorted([x for x in series.posts if x.part > 0], key=lambda x: x.published_on):
                    rows.append((p.title, p.slug, p.published_on))
                rows.append((title, slug, pub_date))
                upsert_hub_series_section(
                    hub_path,
                    series_title=series_title,
                    entries=rows,
                )

            pub = cfg.get("publish", {})
            to_add = [out_path, hub_path]

            if pub.get("enabled") and pub.get("git_commit", True):
                try:
                    publish_git(
                        root,
                        to_add,
                        f"Blog: {title[:60]}",
                        do_commit=True,
                        do_push=bool(pub.get("git_push", True)),
                    )
                    if pub.get("netlify_deploy", False):
                        publish_netlify(root, enabled=True, prod=bool(pub.get("netlify_prod", True)))
                except subprocess.CalledProcessError as exc:
                    print("Git/netlify failed:", exc)
                    out_path.unlink(missing_ok=True)
                    return 1
            else:
                print("Skipping git push (publish disabled or dry run).")

            series.posts.append(
                SeriesPost(
                    slug=slug,
                    title=title,
                    published_on=pub_date,
                    part=part_num,
                    role="part",
                )
            )
            if planned:
                planned.status = "published"
            series.save(state_dir)
            record_publish(state_dir, tz, slug)
            print(
                f"Published part {part_num} (calendar date {pub_date}): {slug} combined: {overall:.1f}"
            )
            return 0

        feedback = "; ".join(h_issues) + " | " + llm_notes
        out_path.unlink(missing_ok=True)
        print(f"Below threshold ({min_q}). Retrying...")

    print("Failed after max attempts. Best combined score:", best_score)
    return 1


def run_catch_up(
    agent_root: Path,
    *,
    dry_run: bool = False,
    ignore_schedule: bool = False,
    max_posts: int = 20,
    as_of: str | None = None,
) -> int:
    """
    Publish every sub-post that is due through ``as_of`` (inclusive), in order, up to ``max_posts``.
    ``as_of`` defaults to today; use ``\"9999-12-31\"`` to backfill all remaining parts 1–3 in one go.
    """
    cfg = load_config(agent_root)
    if dry_run:
        cfg.setdefault("publish", {})
        cfg["publish"]["enabled"] = False
        cfg["publish"]["git_commit"] = False
        cfg["publish"]["git_push"] = False
        cfg["publish"]["netlify_deploy"] = False
    state_dir = agent_root / "state"
    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")
    if not ignore_schedule:
        if not in_publish_hour(cfg, tz):
            print("Outside scheduled publish hour; skipping.")
            return 0
        if not at_minute_past_hour(cfg, tz):
            print("Not on publish minute tick; skipping.")
            return 0
    n_done = 0
    as_of = as_of or today_iso(tz)
    while n_done < max_posts:
        series = WeeklySeriesState.load(state_dir)
        if not series or not series.hub_slug or not series.schedule_anchor_iso:
            if n_done == 0:
                print(
                    "No active weekly series. Run: python -m kcpest_agent start-week "
                    '"Your topic..."',
                )
            return 0
        part_num = next_due_part(series, as_of)
        if part_num is None:
            if n_done:
                print(f"Catch-up finished ({n_done} sub-post(s) this run).")
            return 0
        due = part_due_dates(series.schedule_anchor_iso)
        pub_date = due[part_num]
        print(
            f"Next sub-post: part {part_num} — calendar {pub_date} (as-of {as_of})"
        )
        rc = _try_publish_subpost(
            agent_root,
            dry_run=dry_run,
            part_num=part_num,
            pub_date=pub_date,
        )
        if rc != 0:
            return rc
        n_done += 1
    return 0


def run_once(
    agent_root: Path, *, dry_run: bool = False, ignore_schedule: bool = False
) -> int:
    """At most one sub-post. Same 8:00 / :13 gate as the daemon (unless --any-time)."""
    return run_catch_up(
        agent_root,
        dry_run=dry_run,
        ignore_schedule=ignore_schedule,
        max_posts=1,
        as_of=None,
    )


def backfill_week(
    agent_root: Path,
    user_prompt: str,
    *,
    dry_run: bool = False,
    anchor_iso: str | None = None,
    only_parts: bool = False,
    force: bool = False,
) -> int:
    """
    Create hub (unless ``only_parts``) + all sub-posts in one go.
    ``anchor_iso`` defaults to the Friday before the current ISO week (America/Chicago).
    All posts get ``pubDate`` from anchor +0 / +1 / +3 / +7.
    """
    cfg = load_config(agent_root)
    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")
    if anchor_iso is None:
        a = friday_of_previous_week(tz)
        anchor_iso = a.isoformat()
    if only_parts:
        rc = 0
    else:
        rc = start_week(
            agent_root,
            user_prompt,
            dry_run=dry_run,
            anchor_iso=anchor_iso,
            force=force,
        )
        if rc != 0:
            return rc
    return run_catch_up(
        agent_root,
        dry_run=dry_run,
        ignore_schedule=True,
        max_posts=3,
        as_of="9999-12-31",
    )


def enqueue(agent_root: Path, prompt: str) -> None:
    state_dir = agent_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "pending_prompt.txt").write_text(prompt.strip(), encoding="utf-8")
    print(
        "Saved pending_prompt.txt (legacy). Weekly flow uses: "
        "`start-week \"topic\"` then the daemon for scheduled parts.",
    )


def daemon(agent_root: Path, dry_run: bool = False) -> None:
    cfg = load_config(agent_root)
    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")
    minute_mark = int(cfg.get("schedule", {}).get("publish_minute", 13))
    print(
        f"Weekly-posts daemon: waking each hour at :{minute_mark:02d} "
        f"({tz}); publish attempts only at configured morning hour.",
        flush=True,
    )
    while True:
        try:
            sleep_until_minute_past_hour(tz, minute_mark)
            run_catch_up(agent_root, dry_run=dry_run, max_posts=20, as_of=None)
        except Exception as exc:
            print("run_catch_up error:", exc, file=sys.stderr)
        # small guard so we do not spin if clock is odd
        time.sleep(2)
