# Local content agent (Ollama + search + RAG)

Generates **KC Pest Experts** blog posts as markdown under `src/content/posts/`, validates with `npm run build`, scores quality (heuristic + local LLM), optionally **git commit / push / Netlify deploy**.

## Prerequisites

- **Ollama** running locally with a chat model (e.g. `llama3.2`) and optionally `nomic-embed-text` for better RAG ranking.
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

# 1) Save the weekly theme / user instructions (one line or paragraph)
python -m kcpest_agent enqueue "Why starting pest control in spring beats waiting until summer"

# 2) Run a single generation cycle (respects daily limit & 3pm deadline)
python -m kcpest_agent run-once

# Dry run: build + score only, no git/Netlify
python -m kcpest_agent run-once --dry-run

# 3) Hourly loop (same checks as run-once)
python -m kcpest_agent daemon
```

Use **Launchd** (macOS), **systemd timer**, or **cron** to run `daemon` or `run-once` on a schedule.

## How it works

1. **Queue:** `state/pending_prompt.txt` holds the active topic (updated by `enqueue`).
2. **Calendar week series:** The first post in an ISO week is the **hub** (overview). Later days add **supporting** posts with footer links to the hub and siblings. The hub file gets an **Articles in this series** block (updated when a new part ships).
3. **Daily cap:** At most **one** successful publish per calendar day (`state/daily_log.json`).
4. **Deadline:** No new run after **3:00 PM** local (`schedule.timezone`, default `America/Chicago`) — wait until the next day.
5. **Research:** DuckDuckGo text search + page fetch + `trafilatura` extraction; chunks scored by trusted domains + keyword overlap + optional Ollama embeddings.
6. **Writing:** Ollama returns JSON (`title`, `description`, `body`); front matter matches `src/content.config.ts` including optional `series*` fields.
7. **Validation:** `npm run build` in the Astro project root.
8. **Quality:** Heuristic checklist (build, front matter, word count, external `https://` citations, structure) plus a second Ollama pass for a 0–100 score. Combined score must reach **`min_quality_score`** (default **90**), up to **`max_attempts`** (default **20**).

## Configuration highlights (`config.yaml`)

| Area | Purpose |
|------|--------|
| `project_root` | Path to Astro site (default `..`). |
| `ollama.chat_model` | Main writer. |
| `ollama.embed_model` | Optional; improves chunk ranking. |
| `generation.*` | Word count, min links, attempts, score threshold. |
| `publish.*` | Turn on `git_commit`, `git_push`, `netlify_deploy` when you trust automation. |

## Safety

- Keep `publish.enabled: false` until you have reviewed a few `--dry-run` outputs.
- Review generated citations; models can hallucinate URLs — the pipeline rewards real `https://` links from search context.
- `state/*.json` and `pending_prompt.txt` are gitignored by default.

## Related site docs

See repo root `agent.md` for Astro/Netlify workflow used after a post lands in git.
