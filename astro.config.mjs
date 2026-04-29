import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Step 4.7 — site config + nav routing.
// `site` is required by @astrojs/sitemap to emit absolute URLs and
// drives Astro.site.host inside src/pages/robots.txt.ts.
// `trailingSlash: 'always'` matches the Caddy file_server expectation
// downstream (3.4 cutover).
//
// Note: Astro's built-in i18n config block is intentionally NOT used.
// Per Decision 4 of the i18n decision note, manual parameter routing
// on a single [lang]/ tree owns localisation; only @astrojs/sitemap
// receives the i18n hint (Decision 7).

export default defineConfig({
  site: 'https://aiact.annotated.nl',
  output: 'static',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
  integrations: [
    sitemap({
      i18n: {
        defaultLocale: 'en',
        locales: { en: 'en', nl: 'nl' },
      },
      // Exclude the root meta-refresh stub from the sitemap. The stub
      // already carries `noindex,follow`; the explicit filter keeps
      // the sitemap clean of routes search engines shouldn't index.
      filter: (page) => page !== 'https://aiact.annotated.nl/',
    }),
  ],
});
