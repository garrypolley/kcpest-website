// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || "https://kcpestexperts.com",
  integrations: [
    sitemap({
      filter: (page) => {
        const path = new URL(page).pathname.replace(/\/$/, "") || "/";
        if (path === "/admin" || path === "/thank-you") return false;
        // Blog posts are indexed at /{slug}; /pest-control-blog/{slug} is noindex + canonical to root
        if (path.startsWith("/pest-control-blog/") && path !== "/pest-control-blog") {
          return false;
        }
        return true;
      },
    }),
  ],
  vite: {
    plugins: [tailwindcss()]
  }
});
