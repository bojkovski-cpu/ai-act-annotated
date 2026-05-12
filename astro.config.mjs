import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import fs from 'node:fs';

// ─── Phase 1 redirect map (legacy → canonical) ─────────────────────
//
// Maps legacy URL shapes (chapter-anchored articles, prefixed recitals/
// annexes, the existing /[lang]/history/ tree) to the canonical-id paths
// defined in control-room/reference/url-contract-aiact-2026-05-12.md.
//
// Built programmatically from src/data/*.json because Astro's [param]
// captures the whole path segment — it can't strip literal prefixes like
// "chapter-", "article-", "recital-", "annex-".
//
// Astro emits each redirect as a meta-refresh HTML page in the static
// build. The Caddy reverse proxy in production should layer proper
// HTTP 301 status codes on top for SEO; the meta-refresh + canonical
// <link> below is the fallback that works without server config.

const langs = ['en', 'nl'];
const repoUrl = (p) => new URL(`./${p}`, import.meta.url);
const readJson = (p) => JSON.parse(fs.readFileSync(repoUrl(p), 'utf8'));

const articlesEn = readJson('src/data/articles_en.json');
const recitalsEn = readJson('src/data/recitals_en.json');
const annexesEn  = readJson('src/data/annexes_en.json');
const historyEn  = readJson('src/data/drafting_history_en.json');
const historyNl  = readJson('src/data/drafting_history_nl.json');

const redirects = {};

for (const lang of langs) {
  // Section indexes
  redirects[`/${lang}/articles/`] = `/${lang}/aiact/art/`;
  redirects[`/${lang}/recitals/`] = `/${lang}/aiact/rec/`;
  redirects[`/${lang}/annexes/`]  = `/${lang}/aiact/annex/`;
  redirects[`/${lang}/history/`]  = `/${lang}/aiact/history/`;

  // Article detail: /[lang]/articles/chapter-N/article-M/ → /[lang]/aiact/art/M/
  for (const art of articlesEn) {
    redirects[`/${lang}/articles/chapter-${art.chapter}/article-${art.number}/`] =
      `/${lang}/aiact/art/${art.number}/`;
  }

  // Recital detail: /[lang]/recitals/recital-N/ → /[lang]/aiact/rec/N/
  for (const rec of recitalsEn) {
    redirects[`/${lang}/recitals/recital-${rec.number}/`] =
      `/${lang}/aiact/rec/${rec.number}/`;
  }

  // Annex detail: /[lang]/annexes/annex-{roman}/ → /[lang]/aiact/annex/{roman}/
  for (const ann of annexesEn) {
    const roman = ann.id.toLowerCase();
    redirects[`/${lang}/annexes/annex-${roman}/`] =
      `/${lang}/aiact/annex/${roman}/`;
  }
}

// Chapter detail: /[lang]/articles/chapter-N/ → /[lang]/aiact/chapter/{roman}/
// Derive (number → roman) from the article corpus.
const chapterRoman = new Map();
for (const art of articlesEn) {
  if (!chapterRoman.has(art.chapter)) chapterRoman.set(art.chapter, art.chapter_roman);
}
for (const lang of langs) {
  for (const [num, roman] of chapterRoman) {
    redirects[`/${lang}/articles/chapter-${num}/`] =
      `/${lang}/aiact/chapter/${roman.toLowerCase()}/`;
  }
}

// History — per-stage index and snapshot detail
const histByLang = { en: historyEn, nl: historyNl };
for (const lang of langs) {
  const blob = histByLang[lang];

  // Per-stage index: /[lang]/history/{stage}/ → /[lang]/aiact/history/{stage}/
  for (const stage of blob.stages) {
    redirects[`/${lang}/history/${stage.id}/`] =
      `/${lang}/aiact/history/${stage.id}/`;
  }

  // Snapshot detail per content_type
  for (const snap of blob.snapshots) {
    let legacySlug, newKind, newSlug;
    if (snap.content_type === 'articles') {
      legacySlug = `article-${snap.number}`;
      newKind = 'art';
      newSlug = snap.number;
    } else if (snap.content_type === 'recitals') {
      legacySlug = `recital-${snap.number}`;
      newKind = 'rec';
      newSlug = snap.number;
    } else if (snap.content_type === 'annexes') {
      legacySlug = `annex-${snap.number.toLowerCase()}`;
      newKind = 'annex';
      newSlug = snap.number.toLowerCase();
    } else if (snap.content_type === 'amendments') {
      legacySlug = `amendment-${snap.number}`;
      newKind = 'amendments';
      newSlug = snap.number;
    } else {
      continue;
    }
    redirects[`/${lang}/history/${snap.stage}/${snap.content_type}/${legacySlug}/`] =
      `/${lang}/aiact/history/${snap.stage}/${newKind}/${newSlug}/`;
  }
}

// ─── Step 4.7 — site config + nav routing. (Preserved verbatim.) ───
// `site` is required by @astrojs/sitemap to emit absolute URLs and
// drives Astro.site.host inside src/pages/robots.txt.ts.
// `trailingSlash: 'always'` matches the Caddy file_server expectation
// downstream (3.4 cutover).
//
// Note: Astro's built-in i18n config block is intentionally NOT used.
// Per Decision 4 of the i18n decision note, manual parameter routing
// on a single [lang]/ tree owns localisation; only @astrojs/sitemap
// receives the i18n hint (Decision 7).
//
// Phase 1 (2026-05-12) addition: `redirects` map above ships legacy
// → canonical-id URL transitions per
// control-room/reference/url-contract-aiact-2026-05-12.md.

export default defineConfig({
  site: 'https://aiact.annotated.nl',
  output: 'static',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
  redirects,
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
