from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from slugify import slugify

from kcpest_agent.config import load_config, project_root
from kcpest_agent.generate import assemble_markdown, build_messages, generate_article_json
from kcpest_agent.hub_links import render_series_block, upsert_hub_series_section
from kcpest_agent.quality import (
    combined_score,
    heuristic_score,
    llm_quality_score,
    passes_threshold,
)
from kcpest_agent.search_rag import build_rag_context
from kcpest_agent.series_state import (
    SeriesPost,
    WeeklySeriesState,
    already_published_today,
    before_deadline,
    ensure_series_for_prompt,
    record_publish,
    today_iso,
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
    siblings: list[tuple[str, str]],
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


def run_once(agent_root: Path, *, dry_run: bool = False) -> int:
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
    queue_file = state_dir / "pending_prompt.txt"

    if not queue_file.is_file():
        print("No pending prompt. Use: python -m kcpest_agent enqueue \"Your topic...\"")
        return 1

    user_prompt = queue_file.read_text(encoding="utf-8").strip()
    if not user_prompt:
        print("pending_prompt.txt is empty.")
        return 1

    tz = cfg.get("schedule", {}).get("timezone", "America/Chicago")

    if already_published_today(state_dir, tz):
        print(f"Already published today ({today_iso(tz)}). Skipping.")
        return 0

    if not before_deadline(cfg):
        print("Past daily publish deadline (default 3pm local). Skipping until tomorrow.")
        return 0

    series = ensure_series_for_prompt(state_dir, user_prompt, tz)
    series.save(state_dir)

    ollama = cfg.get("ollama", {})
    base_url = ollama.get("base_url", "http://127.0.0.1:11434")
    chat_model = ollama.get("chat_model", "llama3.2")
    embed_model = ollama.get("embed_model") or None

    gen_cfg = cfg.get("generation", {})
    max_attempts = int(gen_cfg.get("max_attempts", 20))
    min_q = float(gen_cfg.get("min_quality_score", 90))
    min_words = int(gen_cfg.get("min_words", 500))
    min_links = int(gen_cfg.get("min_external_citation_links", 3))

    if series.hub_slug:
        hub_slug = series.hub_slug
    else:
        hub_slug = unique_slug(f"series-overview-{series.topic_id}", posts_dir)

    is_hub = len(series.posts) == 0
    part_num = 0 if is_hub else max(p.part for p in series.posts) + 1
    role = "hub" if is_hub else "part"

    series_title = user_prompt.strip()[:160]

    prior_summary = "\n".join(f"- {p.title}" for p in sorted(series.posts, key=lambda x: x.published_on))

    print("Building RAG context (DuckDuckGo + page fetch + chunking)...")
    rag_text, _docs = build_rag_context(cfg, user_prompt, base_url, embed_model)

    feedback = ""
    best_score = -1.0

    for attempt in range(1, max_attempts + 1):
        print(f"Generation attempt {attempt}/{max_attempts}...")
        messages = build_messages(
            user_prompt=user_prompt,
            rag_context=rag_text,
            role=role,
            series_title=series_title,
            topic_id=series.topic_id,
            hub_slug=hub_slug,
            part_number=part_num,
            prior_posts_summary=prior_summary,
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

        slug = hub_slug if is_hub else unique_slug(title, posts_dir)

        hub_p = next((p for p in series.posts if p.part == 0), None)
        if is_hub:
            body_final = body
        else:
            if not hub_p:
                feedback = "Internal state error: hub missing"
                continue
            sibs = [(hub_p.title, hub_p.slug)]
            for p in sorted([x for x in series.posts if x.part > 0], key=lambda x: x.published_on):
                sibs.append((p.title, p.slug))
            sibs.append((title, slug))
            body_final = append_series_footer(
                body,
                hub_slug=hub_p.slug,
                series_title=series_title,
                current_slug=slug,
                siblings=sibs,
            )

        cover = cfg.get("default_cover_image", "/images/services/general-pest.jpg")
        md = assemble_markdown(
            title=title,
            description=description,
            body=body_final,
            pub_date=today_iso(tz),
            author="KC Pest Experts",
            cover_image=cover,
            cover_alt=title[:120],
            series_topic_id=series.topic_id,
            series_hub_slug=hub_slug,
            series_part=part_num,
            series_title=series_title,
        )

        out_path = posts_dir / f"{slug}.md"
        out_path.write_text(md, encoding="utf-8")

        if is_hub:
            upsert_hub_series_section(
                out_path,
                series_title=series_title,
                entries=[(title, slug)],
            )

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
            if not is_hub:
                hub_path = posts_dir / f"{hub_slug}.md"
                if hub_path.is_file():
                    hub_row = next(p for p in series.posts if p.part == 0)
                    rows = [(hub_row.title, hub_row.slug)]
                    for p in sorted([x for x in series.posts if x.part > 0], key=lambda x: x.published_on):
                        rows.append((p.title, p.slug))
                    rows.append((title, slug))
                    upsert_hub_series_section(
                        hub_path,
                        series_title=series_title,
                        entries=rows,
                    )

            pub = cfg.get("publish", {})
            to_add = [out_path]
            if not is_hub:
                to_add.append(posts_dir / f"{hub_slug}.md")

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

            if is_hub:
                series.hub_slug = slug
            series.posts.append(
                SeriesPost(
                    slug=slug,
                    title=title,
                    published_on=today_iso(tz),
                    part=part_num,
                    role=role,
                )
            )
            series.save(state_dir)
            record_publish(state_dir, tz, slug)
            print("Published:", slug, "combined score:", overall)
            return 0

        feedback = "; ".join(h_issues) + " | " + llm_notes
        out_path.unlink(missing_ok=True)
        print(f"Below threshold ({min_q}). Retrying...")

    print("Failed after max attempts. Best combined score:", best_score)
    return 1


def enqueue(agent_root: Path, prompt: str) -> None:
    state_dir = agent_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "pending_prompt.txt").write_text(prompt.strip(), encoding="utf-8")
    print("Queued topic. Run `run-once` or the hourly daemon to generate.")


def daemon(agent_root: Path, dry_run: bool = False) -> None:
    while True:
        try:
            run_once(agent_root, dry_run=dry_run)
        except Exception as exc:
            print("run_once error:", exc, file=sys.stderr)
        time.sleep(3600)
