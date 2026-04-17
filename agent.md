# KC Pest Website Agent Guide

## Project stack
- Astro static site with Tailwind CSS.
- Content is markdown-first in `src/content/pages` and `src/content/posts`.
- Netlify is the production host (GitHub Pages workflow was removed).

## Day-to-day workflow
1. Run local dev with `netlify dev` (required for redirects/forms parity).
2. Make edits in components/content/assets.
3. Validate with `npm run build`.
4. Commit focused changes with clear, purpose-first message.
5. Push to `origin/main`.
6. Deploy production with `netlify deploy --prod --build`.

## CI/CD pipeline (current)
- Source control: GitHub repo (`main` is deploy branch).
- Build command: `npm run build` (Astro static output to `dist`).
- Runtime/deploy platform: Netlify.
- Production release step used in this project: manual CLI deploy after push:
  - `netlify deploy --prod --build`
- Verify deployment by checking:
  - Production URL: `https://kcpest-website.garrypolley.com`
  - Netlify deploy logs for the latest deploy ID.

## Conventions from this project
- Keep canonical internal links on final routes; use redirects only for legacy SEO paths.
- Keep service/location pages unique in copy and imagery.
- Use concise, conversion-focused CTA language; avoid duplicated visual CTA blocks.
- Keep homepage/service metadata and FAQ schema accurate and customer-facing.
- Prefer small, incremental commits; deploy after meaningful user-visible batches.

## Local blog content agent (`local-content-agent/`)
- Python tool that uses **Ollama**, **DuckDuckGo search**, and optional **embeddings** to draft weekly blog series (hub post + daily supporting posts), runs **`npm run build`** for static validation, scores drafts, and optionally **commits / pushes / Netlify deploys** per `local-content-agent/config.yaml`.
- Setup and CLI: `local-content-agent/README.md`.
- Queue a topic with `enqueue`, then run `run-once` or the hourly `daemon` (respects one post per day and a 3pm local cutoff by default).
