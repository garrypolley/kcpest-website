# Local content agent (Ollama + search + RAG)

Generates **KC Pest Experts** blog posts as markdown under `src/content/posts/`, validates with `npm run build`, scores quality (heuristic + local LLM), optionally **git commit / push / Netlify deploy**.

## Prerequisites

- **Ollama** running locally. Default is **`gemma3:4b`** (~3.3GB). Pull: `ollama pull gemma3:4b`. For **Gemma 4**, upgrade Ollama from [ollama.com/download](https://ollama.com/download) if `ollama pull gemma4:e2b` errors, then set `chat_model` to `gemma4:e2b`. Remove unused huge models to free disk/RAM: `ollama list`, `ollama rm <name>`. Optional: `nomic-embed-text` for RAG.
- **Node 22+** and project dependencies (`npm install` in the site root).
- **Git** and optionally **Netlify CLI** (`netlify`) linked to the site.

## Setup

```bash
cd local-content-agent
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Edit config.yaml — set ollama models, enable publish.* when ready
```

## Commands

```bash
# From local-content-agent/ (with venv active)

# 1) Start the ISO week: hub article + three planned sub-topics (runs immediately when you invoke it)
python -m kcpest_agent start-week "Why starting pest control in spring beats waiting until summer"

# Optional: anchor the hub to a specific calendar day (e.g. last Friday) and/or replace state
# python -m kcpest_agent start-week "…" --anchor-date 2026-04-11 --force

# 1b) Hub + backfill: write hub then generate sub-posts 1–3 in one run, with pubDates from anchor+1/+3/+7
# Default anchor: Friday before the current week (Central). Override with --anchor-date.
# python -m kcpest_agent backfill-week "…" --dry-run
# python -m kcpest_agent backfill-week --only-parts   # existing weekly_series.json, missing parts only

# 2) Try one automated publish (hub is NOT created here — only scheduled parts 1–3)
#    Must be 8:00 AM America/Chicago on the configured minute (default :13) unless you tweak code.
python -m kcpest_agent run-once

# Dry run: build + score only, no git/Netlify
python -m kcpest_agent run-once --dry-run

# 3) Background loop: wake at :13 past each hour; only the morning publish window runs generation.
#    Each valid wake may publish **every** sub-post that is still due (catch-up in one run).
python -m kcpest_agent daemon

# Legacy: writes pending_prompt.txt (weekly flow uses start-week + state/weekly_series.json)
python -m kcpest_agent enqueue "…"
```

Use **Launchd** (macOS), **systemd timer**, or **cron** to keep `daemon` running continuously.

## How it works

1. **Weekly hub (`start-week`):** Writes `state/weekly_series.json` with the hub slug, **`schedule_anchor_iso`** (today), and **three** `planned` sub-post records. The hub markdown includes **Coming up this week** with **Coming soon** lines. Only **one** active topic per ISO week.
2. **Cadence:** Sub-posts **1–3** are due on anchor **+1, +3, and +7** calendar days. The daemon/`run-once` attempts them at **`schedule.publish_hour_central`** (default **8**) on **`publish_minute`** (default **13**), America/Chicago. Each sub-post’s **`pubDate`** in front matter is that **schedule day**, not necessarily “today’s” date (backfill uses historical dates). The hub is a short “trailer”; parts are deep dives with stricter de-duplication against the hub (especially part 1).
3. **Dedup:** Before accepting a draft, the agent checks **Jaccard word-overlap** against prior series bodies (`generation.max_word_overlap_vs_series`; part 1 can use a stricter `max_word_overlap_part1_vs_series`). Part prompts also forbid reusing the overview’s title pattern and H2s.
4. **Daily cap:** At most **one** successful automated publish per calendar day (`state/daily_log.json`).
5. **Research:** DuckDuckGo text search + page fetch + `trafilatura` extraction; chunks scored by trusted domains + keyword overlap + optional Ollama embeddings.
6. **Writing:** Ollama returns JSON (`title`, `description`, `body`); front matter matches `src/content.config.ts` including optional `series*` fields. **On-site CTAs** use only the relative service paths in the prompt (`kcpest_agent/internal_links.py`); the pipeline rewrites any hallucinated `kcpext.com` URLs to the matching `/pest-and-wildlife-services/...` path before save.
7. **Validation:** `npm run build` in the Astro project root.
8. **Quality:** Heuristic checklist (build, front matter, word count, external `https://` citations, structure) plus a second Ollama pass for a 0–100 score. Combined score must reach **`min_quality_score`** (default **90**), up to **`max_attempts`** (default **20**).
9. **Series list / hub block:** The hub’s *Articles in this series* and each part’s footer use **`published_on`** (schedule day). Links are only emitted when that day is on or before “today” in **America/Chicago**; otherwise a **Coming soon:** line (no link) is used—matching the public-by-date rules on the Astro site. Set **`PUBLIC_SHOW_FUTURE_POSTS=true`** in the environment when you want the agent to render all links during drafting.

## Configuration highlights (`config.yaml`)

| Area | Purpose |
|------|--------|
| `project_root` | Path to Astro site (default `..`). |
| `ollama.chat_model` | Main writer. |
| `ollama.embed_model` | Optional; improves chunk ranking. |
| `generation.*` | Word count, min links, attempts, score threshold. |
| `publish.*` | Turn on `git_commit`, `git_push`, `netlify_deploy` when you trust automation. |
| `default_cover_image` | Optional. Omit or leave blank so new posts have **no** hero image (avoids repeating one stock image). |

## Safety

- Keep `publish.enabled: false` until you have reviewed a few `--dry-run` outputs.
- Review generated citations; models can hallucinate URLs — the pipeline rewards real `https://` links from search context.
- `state/*.json` and `pending_prompt.txt` are gitignored by default.

## Related site docs

See repo root `agent.md` for Astro/Netlify workflow used after a post lands in git.
