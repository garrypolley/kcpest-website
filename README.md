# kcpest-website

Rebuild of the KC Pest Experts website as a static Astro + Tailwind site with Git-backed markdown content.

## Project goals
- Crawl and archive the existing `www.kcpestexperts.com` site.
- Migrate content into markdown collections.
- Launch a fast static site on GitHub Pages.
- Provide a simple CMS editing experience with Decap CMS.

## Quick start
```bash
npm install
npm run dev
```

## Crawl and import workflow
```bash
./tools/crawl-site.sh
python3 ./tools/import_content.py --inventory ./data/content-inventory.json --repo-root .
python3 ./tools/fix_frontmatter.py
```

## Structure
- `tools/` - crawl and content extraction scripts
- `data/` - mirrored source content and generated inventories
- `docs/` - migration notes, URL mapping, and audits
- `src/content/` - markdown source for pages and blog posts
- `public/admin/` - Decap CMS configuration
