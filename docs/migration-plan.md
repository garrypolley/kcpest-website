# Migration Implementation Notes

This repository follows a phased migration approach:

1. Crawl and archive public content from `https://www.kcpestexperts.com`.
2. Extract readable text and metadata into an inventory file.
3. Rebuild pages as markdown-driven Astro routes.
4. Validate content parity and links locally.
5. Deploy static output via GitHub Pages with custom domain.

See `docs/url-mapping.md` and `docs/migration-audit.md` for migration progress.
