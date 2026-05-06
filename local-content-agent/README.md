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
#    During the publish **hour** (default 8 Central) and **minute window**
#    (default any time from :13 through end of that hour; see config `publish_exact_minute`).
#    Or use --any-time when testing.
python -m kcpest_agent run-once

# Dry run: build + score only, no git/Netlify
python -m kcpest_agent run-once --dry-run

# 3) Background loop: wake at :13 past each hour; only runs generation in the morning publish hour.
#    **Nothing happens if this process is not running.** Use Login Item, launchd, systemd, or cron.
#    Each eligible wake may publish every sub-post that is still due (catch-up).
python -m kcpest_agent daemon

# Legacy: writes pending_prompt.txt (weekly flow uses start-week + state/weekly_series.json)
python -m kcpest_agent enqueue "…"
```

Use **launchd**, **systemd**, or **cron** so something runs `daemon` or `run-once` reliably (see below). Leaving a Terminal tab open alone is brittle if the Mac sleeps.

## Automatic publish checklist (why “nothing deployed” happens)

Publishing to **GitHub** and the live site is **two separate knobs**:

1. **`publish.enabled: true`** in `local-content-agent/config.yaml`  
   If this stays false (matching `config.example.yaml`), the agent only writes markdown locally and prints *Skipping git push* — matches “I have to run git / Netlify myself.”

2. **Something must trigger the scheduler** regularly:
   - **`python -m kcpest_agent daemon`** is an infinite loop. If it is not running (machine off, sleeps, Terminal closed), no morning job runs until you invoke `run-once`/`daemon` again.
   - **Alternative:** add a cron line (shown below) so `run-once` fires daily without a long-lived process — still requires `publish.enabled: true` for pushes.

3. **Netlify from Git:** If GitHub triggers Netlify builds on `main`, you usually do **not** need `netlify_deploy: true` — `git_push: true` is enough. Use `netlify_deploy` only if you rely on the Netlify CLI.

4. **Ollama** must be up when the job runs; otherwise generation fails and nothing is committed.

### Cron example (macOS/Linux, America/Chicago)

Runs one catch-up pass every weekday at 8:20 Central (adjust paths):

```cron
TZ=America/Chicago
20 8 * * * cd /path/to/kcpest-website/local-content-agent && . .venv/bin/activate && python -m kcpest_agent run-once >> state/cron.log 2>&1
```

With the default **relaxed minute window** (`publish_exact_minute: false`), any time from **8:13 through 8:59** is valid in the 8 a.m. hour.

## How it works

1. **Weekly hub (`start-week`):** Writes `state/weekly_series.json` with the hub slug, **`schedule_anchor_iso`** (today), and **three** `planned` sub-post records. The hub markdown includes **Coming up this week** with **Coming soon** lines. Only **one** active topic per ISO week.
2. **Cadence:** Sub-posts **1–3** are due on anchor **+1, +3, and +7** calendar days. The daemon/`run-once` attempts them at **`schedule.publish_hour_central`** (default **8**) during the **minute window** described in `config.example.yaml` (default: from **:13** through the rest of that hour unless `publish_exact_minute: true`). Each sub-post’s **`pubDate`** in front matter is that **schedule day**, not necessarily “today’s” date (backfill uses historical dates). The hub is a short “trailer”; parts are deep dives with stricter de-duplication against the hub (especially part 1).
3. **Dedup:** Before accepting a draft, the agent checks **Jaccard word-overlap** against prior series bodies (`generation.max_word_overlap_vs_series`; part 1 can use a stricter `max_word_overlap_part1_vs_series`). Part prompts also forbid reusing the overview’s title pattern and H2s.
4. **Run log:** `state/daily_log.json` records the last successful publish slug/date (not a hard throttle for future runs).
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
| `schedule.publish_minute` | First minute in the hour that counts as “open” (default 13). |
| `schedule.publish_exact_minute` | `true` = only that exact minute (old behavior). `false` = from that minute through ``publish_window_end_minute`` or end of hour (default). |
| `schedule.publish_window_end_minute` | Optional cap (inclusive) on the minute window within the publish hour. |
| `publish.*` | Set **`enabled: true`** for unattended `git commit/push`. `netlify_deploy` only if you deploy via CLI instead of Git-triggered builds. |
| `default_cover_image` | Optional. Omit or leave blank so new posts have **no** hero image (avoids repeating one stock image). |

## Safety

- Keep `publish.enabled: false` until you have reviewed a few `--dry-run` outputs.
- Review generated citations; models can hallucinate URLs — the pipeline rewards real `https://` links from search context.
- `state/*.json` and `pending_prompt.txt` are gitignored by default.

## Related site docs

See repo root `agent.md` for Astro/Netlify workflow used after a post lands in git.
