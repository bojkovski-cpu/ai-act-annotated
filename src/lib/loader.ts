/**
 * AI Act Annotated Edition — Data loader (build-time JSON imports).
 *
 * Step 4.3b: single point of access for all canonical-text data
 * (articles, recitals, annexes, chapters) + the language-agnostic
 * cross-references and Omnibus amendments. Every page and component
 * that previously imported `@data/ai_act_structured.json` now imports
 * from here.
 *
 * Restored at step 4.7 from a prior truncation (see step-4.7
 * completion notes).
 */

import type {
  Lang,
  Article,
  Recital,
  Annex,
  Chapter,
  CrossReferences,
  OmnibusAmendment,
  DraftingHistory,
  DraftingStage,
  DraftingSnapshot,
  DraftingHistoryGap,
  BilingualText,
  GuidanceDoc,
  GuidanceCitation,
  InternalReference,
  ExternalReference,
  InternalReverseReference,
} from '@/types/aiact';

// ─── Build-time JSON imports ───────────────────────────────────────

import articles_en from '@data/articles_en.json';
import articles_nl from '@data/articles_nl.json';
import recitals_en from '@data/recitals_en.json';
import recitals_nl from '@data/recitals_nl.json';
import annexes_en from '@data/annexes_en.json';
import annexes_nl from '@data/annexes_nl.json';
import cross_references_data from '@data/cross_references.json';
import omnibus_amendments_en from '@data/omnibus_amendments_en.json';
import drafting_history_en from '@data/drafting_history_en.json';
import drafting_history_nl from '@data/drafting_history_nl.json';
import guidance_data from '@data/guidance.json';
import guidance_index_data from '@data/guidance_index_by_article.json';

// Eagerly load guidance body markdown via Vite's import.meta.glob. The `?raw`
// query returns the file contents as a string; `eager: true` makes the import
// synchronous so getGuidanceBody() can be called from frontmatter without
// awaiting. The path pattern matches src/content/guidance/<lang>/<id>.md, which
// is where scripts/build_guidance.py copies the parsed bodies on each rebuild.
const guidance_body_modules = import.meta.glob<string>(
  '/src/content/guidance/**/*.md',
  { query: '?raw', import: 'default', eager: true },
);

// ─── Typed casts ───────────────────────────────────────────────────

const articlesMap: Record<Lang, Article[]> = {
  en: articles_en as unknown as Article[],
  nl: articles_nl as unknown as Article[],
};

const recitalsMap: Record<Lang, Recital[]> = {
  en: recitals_en as unknown as Recital[],
  nl: recitals_nl as unknown as Recital[],
};

const annexesMap: Record<Lang, Annex[]> = {
  en: annexes_en as unknown as Annex[],
  nl: annexes_nl as unknown as Annex[],
};

const crossReferences = cross_references_data as unknown as CrossReferences;
const omnibusAmendments = omnibus_amendments_en as unknown as OmnibusAmendment[];

const draftingHistoryMap: Record<Lang, DraftingHistory> = {
  en: drafting_history_en as unknown as DraftingHistory,
  nl: drafting_history_nl as unknown as DraftingHistory,
};

const guidanceDocs = guidance_data as unknown as GuidanceDoc[];
const guidanceIndex = guidance_index_data as unknown as Record<
  string,
  GuidanceCitation[]
>;

// ─── Sort helpers ──────────────────────────────────────────────────

function numericKey(s: string): number {
  const m = /^(\d+)/.exec(s);
  return m ? parseInt(m[1], 10) : 0;
}

// ─── Articles ──────────────────────────────────────────────────────

export function getArticles(lang: Lang): Article[] {
  return [...articlesMap[lang]].sort(
    (a, b) => numericKey(a.number) - numericKey(b.number),
  );
}

export function getArticle(lang: Lang, number: string): Article | undefined {
  return articlesMap[lang].find((a) => a.number === number);
}

// ─── Recitals ──────────────────────────────────────────────────────

export function getRecitals(lang: Lang): Recital[] {
  return [...recitalsMap[lang]].sort(
    (a, b) => numericKey(a.number) - numericKey(b.number),
  );
}

export function getRecital(lang: Lang, number: string): Recital | undefined {
  return recitalsMap[lang].find((r) => r.number === number);
}

// ─── Annexes ───────────────────────────────────────────────────────

const ROMAN_ORDER: Record<string, number> = {
  I: 1, II: 2, III: 3, IV: 4, V: 5, VI: 6, VII: 7,
  VIII: 8, IX: 9, X: 10, XI: 11, XII: 12, XIII: 13,
};

export function getAnnexes(lang: Lang): Annex[] {
  return [...annexesMap[lang]].sort(
    (a, b) => (ROMAN_ORDER[a.id] ?? 999) - (ROMAN_ORDER[b.id] ?? 999),
  );
}

export function getAnnex(lang: Lang, id: string): Annex | undefined {
  const upper = id.toUpperCase();
  return annexesMap[lang].find((x) => x.id === upper);
}

// ─── Chapters ──────────────────────────────────────────────────────

export function getChapters(lang: Lang): Chapter[] {
  const map = new Map<number, Chapter>();
  for (const a of getArticles(lang)) {
    let ch = map.get(a.chapter);
    if (!ch) {
      ch = {
        number: a.chapter,
        roman: a.chapter_roman,
        title: a.chapter_title,
        articles: [],
      };
      map.set(a.chapter, ch);
    }
    ch.articles.push(a.number);
  }
  return [...map.values()].sort((a, b) => a.number - b.number);
}

// ─── Cross references ──────────────────────────────────────────────

export function getRelatedRecitals(
  articleNumber: string,
  lang: Lang,
): Recital[] {
  const numericNums = crossReferences.article_to_recitals[articleNumber] ?? [];
  const recitals = recitalsMap[lang];
  const out: Recital[] = [];
  for (const n of numericNums) {
    const match = recitals.find((r) => r.number === String(n));
    if (match) out.push(match);
  }
  out.sort((a, b) => numericKey(a.number) - numericKey(b.number));
  return out;
}

export function getCrossReferences(): CrossReferences {
  return crossReferences;
}

// ─── Article references (4.9b) ─────────────────────────────────────
//
// The structured indexes are language-agnostic — article numbers are the
// same in EN and NL. The `lang` parameter is accepted for symmetry with
// the rest of the loader API and reserved for downstream URL composition
// (external EUR-Lex links use ?LANG=EN / ?LANG=NL); it's intentionally
// unused inside the lookup itself.
//
// Returns empty arrays when an article has no entries — components do
// not need to defensively coalesce against undefined.

export function getInternalReferencesFor(
  articleNumber: string,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _lang: Lang,
): InternalReference[] {
  const idx = crossReferences.article_to_articles_internal;
  if (!idx) return [];
  return idx[articleNumber] ?? [];
}

export function getExternalReferencesFor(
  articleNumber: string,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _lang: Lang,
): ExternalReference[] {
  const idx = crossReferences.article_to_external_refs;
  if (!idx) return [];
  return idx[articleNumber] ?? [];
}

export function getArticlesReferencing(
  articleNumber: string,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _lang: Lang,
): InternalReverseReference[] {
  const idx = crossReferences.articles_referencing;
  if (!idx) return [];
  return idx[articleNumber] ?? [];
}

/**
 * Look up an article's chapter number by its number. Used by the
 * renderer to compose `/articles/chapter-NN/article-NN/` URLs for
 * internal references without baking chapter into every JSON entry.
 *
 * Returns null if the article number is not in the corpus (defensive
 * — should never happen for valid internal references, but the parser
 * does not validate target existence).
 */
export function getChapterForArticle(articleNumber: string): number | null {
  // EN list is the authoritative source (article numbers are language-
  // agnostic, but we have to pick one). Chapter assignment is identical
  // across EN and NL by construction.
  const found = articlesMap.en.find((a) => a.number === articleNumber);
  return found ? found.chapter : null;
}

// ─── Omnibus amendments ────────────────────────────────────────────

export function getOmnibusAmendmentsForArticle(
  articleNumber: string,
): OmnibusAmendment[] {
  return omnibusAmendments.filter((a) => a.article_number === articleNumber);
}

// ─── Static-paths helpers ──────────────────────────────────────────

const LANGS: Lang[] = ['en', 'nl'];

export function getArticlePagePaths(): Array<{
  params: { lang: Lang; chapter: string; article: string };
  props: { article: Article };
}> {
  const out: Array<{
    params: { lang: Lang; chapter: string; article: string };
    props: { article: Article };
  }> = [];
  for (const lang of LANGS) {
    for (const article of getArticles(lang)) {
      out.push({
        params: {
          lang,
          chapter: `chapter-${article.chapter}`,
          article: `article-${article.number}`,
        },
        props: { article },
      });
    }
  }
  return out;
}

export function getRecitalPagePaths(): Array<{
  params: { lang: Lang; recital: string };
  props: { recital: Recital };
}> {
  const out: Array<{
    params: { lang: Lang; recital: string };
    props: { recital: Recital };
  }> = [];
  for (const lang of LANGS) {
    for (const recital of getRecitals(lang)) {
      out.push({
        params: { lang, recital: `recital-${recital.number}` },
        props: { recital },
      });
    }
  }
  return out;
}

export function getAnnexPagePaths(): Array<{
  params: { lang: Lang; annex: string };
  props: { annex: Annex };
}> {
  const out: Array<{
    params: { lang: Lang; annex: string };
    props: { annex: Annex };
  }> = [];
  for (const lang of LANGS) {
    for (const annex of getAnnexes(lang)) {
      out.push({
        params: { lang, annex: `annex-${annex.id.toLowerCase()}` },
        props: { annex },
      });
    }
  }
  return out;
}

export function getChapterPagePaths(): Array<{
  params: { lang: Lang; chapter: string };
  props: { chapter: Chapter };
}> {
  const out: Array<{
    params: { lang: Lang; chapter: string };
    props: { chapter: Chapter };
  }> = [];
  for (const lang of LANGS) {
    for (const chapter of getChapters(lang)) {
      out.push({
        params: { lang, chapter: `chapter-${chapter.number}` },
        props: { chapter },
      });
    }
  }
  return out;
}

export function getIndexPagePaths(): Array<{ params: { lang: Lang } }> {
  return LANGS.map((lang) => ({ params: { lang } }));
}

// ─── Drafting history (4.4) ────────────────────────────────────────

export function getDraftingHistory(lang: Lang): DraftingHistory {
  return draftingHistoryMap[lang];
}

export function getDraftingStages(lang: Lang): DraftingStage[] {
  return [...draftingHistoryMap[lang].stages].sort((a, b) => a.order - b.order);
}

export function getDraftingSnapshotsForArticle(
  articleNumber: string,
  lang: Lang,
): DraftingSnapshot[] {
  const all = draftingHistoryMap[lang].snapshots;
  const stageOrder: Record<string, number> = {};
  for (const s of draftingHistoryMap[lang].stages) stageOrder[s.id] = s.order;
  return all
    .filter((s) => s.content_type === 'articles' && s.number === articleNumber)
    .sort((a, b) => (stageOrder[a.stage] ?? 99) - (stageOrder[b.stage] ?? 99));
}

export function getDraftingSnapshotsForRecital(
  recitalNumber: string,
  lang: Lang,
): DraftingSnapshot[] {
  const all = draftingHistoryMap[lang].snapshots;
  const stageOrder: Record<string, number> = {};
  for (const s of draftingHistoryMap[lang].stages) stageOrder[s.id] = s.order;
  return all
    .filter((s) => s.content_type === 'recitals' && s.number === recitalNumber)
    .sort((a, b) => (stageOrder[a.stage] ?? 99) - (stageOrder[b.stage] ?? 99));
}

export function getDraftingSnapshotsForAnnex(
  annexId: string,
  lang: Lang,
): DraftingSnapshot[] {
  const all = draftingHistoryMap[lang].snapshots;
  const upper = annexId.toUpperCase();
  return all.filter((s) => s.content_type === 'annexes' && s.number === upper);
}

export function getDraftingAmendmentsForArticle(
  articleNumber: string,
  lang: Lang,
): DraftingSnapshot[] {
  const all = draftingHistoryMap[lang].snapshots;
  return all
    .filter(
      (s) =>
        s.content_type === 'amendments' &&
        s.amends_kind === 'article' &&
        s.amends_number === articleNumber,
    )
    .sort((a, b) => numericKey(a.number) - numericKey(b.number));
}

export function getDraftingAmendmentsForRecital(
  recitalNumber: string,
  lang: Lang,
): DraftingSnapshot[] {
  const all = draftingHistoryMap[lang].snapshots;
  return all
    .filter(
      (s) =>
        s.content_type === 'amendments' &&
        s.amends_kind === 'recital' &&
        s.amends_number === recitalNumber,
    )
    .sort((a, b) => numericKey(a.number) - numericKey(b.number));
}

export function getDraftingAmendmentsForAnnex(
  annexId: string,
  lang: Lang,
): DraftingSnapshot[] {
  const all = draftingHistoryMap[lang].snapshots;
  const upper = annexId.toUpperCase();
  return all
    .filter(
      (s) =>
        s.content_type === 'amendments' &&
        s.amends_kind === 'annex' &&
        s.amends_number === upper,
    )
    .sort((a, b) => numericKey(a.number) - numericKey(b.number));
}

export function getDraftingAmendment(
  amendmentNumber: string,
  lang: Lang,
): DraftingSnapshot | undefined {
  return draftingHistoryMap[lang].snapshots.find(
    (s) =>
      s.content_type === 'amendments' && s.number === amendmentNumber,
  );
}

export function getDraftingHistoryGaps(
  number: string,
  contentType: 'articles' | 'recitals' | 'annexes',
): DraftingHistoryGap[] {
  const gaps: DraftingHistoryGap[] = [];
  const stages = draftingHistoryMap.en.stages.map((s) => s.id);
  const target = contentType === 'annexes' ? number.toUpperCase() : number;
  for (const stage of stages) {
    const inEn = draftingHistoryMap.en.snapshots.some(
      (s) => s.stage === stage && s.content_type === contentType && s.number === target,
    );
    const inNl = draftingHistoryMap.nl.snapshots.some(
      (s) => s.stage === stage && s.content_type === contentType && s.number === target,
    );
    if (inEn && !inNl) gaps.push({ stage, missing_in: 'nl' });
    else if (inNl && !inEn) gaps.push({ stage, missing_in: 'en' });
  }
  return gaps;
}

// ─── Drafting-history static-paths helpers ─────────────────────────

export function getDraftingSnapshotPagePaths(
  contentType: 'articles' | 'recitals' | 'annexes',
): Array<{
  params: { lang: Lang; version: string; number: string };
  props: { snapshot: DraftingSnapshot };
}> {
  const out: Array<{
    params: { lang: Lang; version: string; number: string };
    props: { snapshot: DraftingSnapshot };
  }> = [];
  for (const lang of LANGS) {
    for (const snap of draftingHistoryMap[lang].snapshots) {
      if (snap.content_type !== contentType) continue;
      const numberSlug =
        contentType === 'annexes'
          ? `annex-${snap.number.toLowerCase()}`
          : contentType === 'articles'
            ? `article-${snap.number}`
            : `recital-${snap.number}`;
      out.push({
        params: { lang, version: snap.stage, number: numberSlug },
        props: { snapshot: snap },
      });
    }
  }
  return out;
}

export function getDraftingAmendmentPagePaths(): Array<{
  params: { lang: Lang; version: string; number: string };
  props: { snapshot: DraftingSnapshot };
}> {
  const out: Array<{
    params: { lang: Lang; version: string; number: string };
    props: { snapshot: DraftingSnapshot };
  }> = [];
  for (const lang of LANGS) {
    for (const snap of draftingHistoryMap[lang].snapshots) {
      if (snap.content_type !== 'amendments') continue;
      out.push({
        params: { lang, version: snap.stage, number: `amendment-${snap.number}` },
        props: { snapshot: snap },
      });
    }
  }
  return out;
}

export function getDraftingStagePagePaths(): Array<{
  params: { lang: Lang; version: string };
  props: { stage: DraftingStage };
}> {
  const out: Array<{
    params: { lang: Lang; version: string };
    props: { stage: DraftingStage };
  }> = [];
  for (const lang of LANGS) {
    for (const stage of draftingHistoryMap[lang].stages) {
      out.push({
        params: { lang, version: stage.id },
        props: { stage },
      });
    }
  }
  return out;
}

// ─── Guidance (5.2) ────────────────────────────────────────────────

export function getGuidanceDocs(): GuidanceDoc[] {
  return [...guidanceDocs].sort((a, b) => {
    const da = (a.adoption_date ?? '').replace(/-/g, '');
    const db = (b.adoption_date ?? '').replace(/-/g, '');
    if (da !== db) return db.localeCompare(da);
    return (a.canonical_id ?? '').localeCompare(b.canonical_id ?? '');
  });
}

export function getGuidanceDoc(canonicalId: string): GuidanceDoc | undefined {
  return guidanceDocs.find((d) => d.canonical_id === canonicalId);
}

export function getGuidanceTitleFor(
  doc: GuidanceDoc,
  lang: Lang,
): { value: string; resolved_lang: Lang } {
  const direct = doc.title?.[lang];
  if (typeof direct === 'string' && direct.length > 0) {
    return { value: direct, resolved_lang: lang };
  }
  for (const candidate of doc.languages) {
    const val = doc.title?.[candidate];
    if (typeof val === 'string' && val.length > 0) {
      return { value: val, resolved_lang: candidate };
    }
  }
  return { value: doc.title?.en ?? doc.canonical_id, resolved_lang: 'en' };
}

export function getGuidanceUrlFor(doc: GuidanceDoc, lang: Lang): string | null {
  const url = doc.url;
  if (!url) return null;
  if (typeof url === 'string') return url;
  const direct = url[lang];
  if (typeof direct === 'string' && direct.length > 0) return direct;
  for (const candidate of doc.languages) {
    const val = (url as BilingualText)[candidate];
    if (typeof val === 'string' && val.length > 0) return val;
  }
  return null;
}

export function getGuidanceBodyPath(
  doc: GuidanceDoc,
  lang: Lang,
): string | null {
  const path = doc.body_paths?.[lang];
  return path ?? null;
}

export function getGuidanceBody(
  canonicalId: string,
  lang: Lang,
): string | undefined {
  const doc = getGuidanceDoc(canonicalId);
  if (!doc) return undefined;
  const rel = doc.body_paths?.[lang];
  if (!rel) return undefined;
  const key = `/src/content/${rel}`;
  const body = guidance_body_modules[key];
  return typeof body === 'string' ? body : undefined;
}

export function getGuidanceCitationsForArticle(
  articleNumber: string | number,
  lang: Lang,
): GuidanceCitation[] {
  const key = String(articleNumber);
  const entries = guidanceIndex[key];
  if (!entries) return [];
  return entries.filter((e) => e.language === lang);
}

export function getGuidancePagePaths(): Array<{
  params: { lang: Lang; slug: string };
  props: { doc: GuidanceDoc };
}> {
  const out: Array<{
    params: { lang: Lang; slug: string };
    props: { doc: GuidanceDoc };
  }> = [];
  for (const doc of guidanceDocs) {
    for (const lang of LANGS) {
      if (doc.body_paths?.[lang]) {
        out.push({
          params: { lang, slug: doc.canonical_id },
          props: { doc },
        });
      }
    }
  }
  return out;
}

export function getCitedArticlesForGuidance(
  canonicalId: string,
  lang: Lang,
): string[] {
  const set = new Set<string>();
  for (const [articleNumber, entries] of Object.entries(guidanceIndex)) {
    for (const e of entries) {
      if (e.guidance_id === canonicalId && e.language === lang) {
        set.add(articleNumber);
        break;
      }
    }
  }
  return [...set].sort((a, b) => numericKey(a) - numericKey(b));
}
