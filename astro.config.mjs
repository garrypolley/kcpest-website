// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || "https://kcpest-website.garrypolley.com",
  vite: {
    plugins: [tailwindcss()]
  }
});