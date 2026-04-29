/**
 * EU AI Act Annotated Edition — shared TypeScript types.
 *
 * Step 4.3b: extended from the 4.2 minimal stub (Lang only) to cover the
 * canonical-text entities (Article, Recital, Annex, Chapter), the per-article
 * Omnibus amendment record, and the language-agnostic CrossReference map.
 *
 * Types are derived from the actual data shape in src/data/*.json — they are
 * NOT imported from the GDPR snapshot's types/gdpr.ts, which describes the
 * GDPR's content shape (different entity model: schema-v3 with versions,
 * canonical_ids, validity windows). The AI Act stays on a flat one-version
 * shape until 4.4 introduces drafting-history snapshots.
 *
 * Number normalisation: all entity numbers (article.number, recital.number,
 * paragraph.number) are STRINGS at the data layer. EN data was numeric in
 * the legacy ai_act_structured.json blob; the bridge scripts normalise to
 * string for symmetry with the NL corpus and to leave headroom for letter-
 * suffixed numbers (e.g. Omnibus's new Article 4a / 60a, when those land).
 */

export type Lang = 'en' | 'nl';

// ─── Paragraph ────────────────────────────────────────────────────────

/**
 * A single paragraph within an article. EN articles ship with structured
 * paragraphs from the parser; NL articles are parsed by build_nl_blobs.py
 * out of the body_md blob into the same shape.
 *
 * `id` and `number` are nullable: articles without numbered paragraphs (e.g.
 * Article 3 Definitions, Article 4 AI literacy) collapse to a single row
 * with both fields null and the entire body in `text`.
 */
export interface Paragraph {
  id: string | null;
  number: string | null;
  text: string;
}

// ─── Article ──────────────────────────────────────────────────────────

export interface Article {
  number: string;
  label: string;
  title: string;
  paragraphs: Paragraph[];
  chapter: number;
  chapter_roman: string;
  chapter_title: string;
  /** Recital numbers cross-referenced from this article. EN-side data only;
   * the loader exposes language-resolved Recital objects via
   * getRelatedRecitals(articleNumber, lang). */
  related_recitals?: number[];
  /**
   * Pre-4.4 EN articles still carry this embedded blob (legacy). After 4.4 it
   * is no longer authoritative — drafting history lives in
   * src/data/drafting_history_{en,nl}.json and is accessed via
   * getDraftingSnapshotsForArticle(article.number, lang). The field stays
   * typed-out here so older readers don't break, but ArticleBlock no longer
   * reads it; treat it as deprecated and drop it from articles_en.json in a
   * follow-up cleanup pass.
   * @deprecated since 4.4 — use loader's drafting-history accessors instead.
   */
  drafting_history?: Record<string, string | null | undefined>;
}

// ─── Drafting history (4.4) ──────────────────────────────────────────

/**
 * One legislative phase in the AI Act's drafting history. The same stage row
 * appears in both drafting_history_en.json and drafting_history_nl.json (the
 * stages are language-agnostic; only the per-locale labels differ).
 *
 * `final-2024` is intentionally omitted — the live regulation IS the final
 * stage and the timeline reads it from getArticles(lang) / getRecitals(lang)
 * directly (Q B resolution recorded in step-4.4-paused-2026-04-28.md).
 */
export interface DraftingStage {
  /** Stable URL slug, e.g. "commission-2021", "parliament-2023". */
  id: string;
  label_en: string;
  label_nl: string;
  /** ISO date of the published version, e.g. "2021-04-21". */
  date: string;
  /** Human-readable provenance label, e.g. "COM(2021) 206 final". */
  source_label: string;
  /** Render order on the timeline (1 = earliest). */
  order: number;
}

/**
 * One stage × content_type × number row. The flat snapshots[] array contains
 * every published stage of every entity that the source corpus supports for
 * the given language. Renderers filter by stage and content_type at draw time.
 *
 * Asymmetric coverage between EN and NL is first-class: the NL file may have
 * a snapshot the EN file does not (e.g. commission-2021 annexes; commission-
 * 2021 recital 12) and vice versa. The renderer reconciles via
 * getDraftingHistoryGaps() and surfaces a Decision-3 disclosure block.
 *
 * Amendments (parliament-2023) carry additional `amends_*` fields describing
 * which provision the amendment touches. The 4.3c re-ingestion produced
 * symmetric 771-entry trees in both languages.
 */
export interface DraftingSnapshot {
  /** Deterministic from (stage, content_type, number). Use for URL anchors
   *  and reverse lookups. */
  snapshot_id: string;
  stage: string;            // matches DraftingStage.id
  content_type: 'articles' | 'recitals' | 'annexes' | 'amendments';
  /** Article/recital/amendment number as a string. Annex number is roman
   *  ("I", "II", ..., "IX"). */
  number: string;
  /** Articles and amendments may have a title (or display label). Recitals
   *  do not. */
  title: string | null;
  /** Body text. Plain prose for articles/recitals/annexes; full markdown
   *  (with the four-column EUR-Lex layout) for amendments. */
  text: string;
  // Amendments-only fields (parliament-2023):
  amends_kind?: 'article' | 'recital' | 'annex' | 'structural';
  amends_number?: string;             // base number, e.g. "29" for Article 29
  amends_paragraph?: string;          // e.g. "1" for "paragraph 1"
  amends_suffix?: string;             // "a" / "bis" / etc. for new sub-entities
  amends_paragraph_suffix?: string;
  amends_target_text?: string;        // raw "amendment_target" string from EUR-Lex
}

/**
 * The shape of src/data/drafting_history_{en,nl}.json after 4.4. Both
 * languages share this top-level shape; populated content varies by locale.
 */
export interface DraftingHistory {
  stages: DraftingStage[];
  snapshots: DraftingSnapshot[];
}

/**
 * For a given (article|recital|annex, kind) pair, which stages have a
 * snapshot in EN but not NL, or NL but not EN. The renderer uses this to
 * decide where to show the Decision-3 disclosure block. Bidirectional —
 * EN-side gaps are first-class (commission-2021 has more NL coverage in
 * places, see step-4.4-paused-2026-04-28.md).
 */
export interface DraftingHistoryGap {
  stage: string;             // matches DraftingStage.id
  missing_in: Lang;          // 'en' or 'nl'
}

// ─── Recital ──────────────────────────────────────────────────────────

export interface Recital {
  number: string;
  text: string;
}

// ─── Annex ────────────────────────────────────────────────────────────

export interface Annex {
  /** Roman-numeral identifier, e.g. "I", "II", "XIII". */
  id: string;
  title: string;
  text: string;
}

// ─── Chapter ──────────────────────────────────────────────────────────

/**
 * Chapter list entry. Chapter numbers and roman numerals are language-
 * agnostic; titles vary per language (loader returns the language-matched
 * chapter list via getChapters(lang)).
 *
 * `articles` is the list of article numbers in this chapter, in regulation
 * order. Used by Sidebar to build the chapter→article tree without
 * re-scanning the full article list.
 */
export interface Chapter {
  number: number;
  roman: string;
  title: string;
  articles: string[];
}

// ─── Omnibus amendment ────────────────────────────────────────────────

/**
 * A single proposed amendment from COM(2025) 836 final (the AI Omnibus).
 * Stored in src/data/omnibus_amendments_en.json — flat list, each entry
 * tagged with the source article_number it affects.
 *
 * EN-only at step 4.3b. On /nl/ pages, the Omnibus tab renders the EN
 * body with a Dutch chrome label ("Bron: COM(2025) 836 — beschikbaar in
 * het Engels") per the 4.3b decision recorded with Pavle.
 */
export interface OmnibusAmendment {
  article_number: string;
  paragraph: number | string;
  sub_provision: string | null;
  action: string;
  summary: string;
}

// ─── Cross references ─────────────────────────────────────────────────

/**
 * Bidirectional article↔recital reference map, language-agnostic. Lifted
 * verbatim from the legacy ai_act_structured.json blob.
 *
 * Keys are stringified numbers (the original blob used numeric keys but
 * JSON serialisation flattens them to strings). Values are arrays of
 * numbers identifying the related entities.
 *
 * Step 4.9a extends the shape with three new top-level keys produced by
 * scripts/extract_article_references.py: internal article-to-article
 * references, external (GDPR + other instruments) references, and the
 * reverse "who cites this article" index. The legacy keys are
 * preserved verbatim — the parser only adds; never modifies.
 */
export interface CrossReferences {
  article_to_recitals: Record<string, number[]>;
  recital_to_articles: Record<string, number[]>;
  article_to_articles_internal?: Record<string, InternalReference[]>;
  article_to_external_refs?: Record<string, ExternalReference[]>;
  articles_referencing?: Record<string, InternalReverseReference[]>;
}

/**
 * Source-text location of a single reference. `paragraph` is the article's
 * paragraph number (e.g. "1", "2"); `letter` is the sub-point label
 * (e.g. "a", "b") or null when the reference appears in the paragraph
 * intro rather than inside a labelled sub-point.
 */
export interface ReferenceLocation {
  paragraph: string | null;
  letter: string | null;
}

/**
 * One internal article reference made FROM the article keyed in
 * `article_to_articles_internal`. `target_kind` is `"article"` for
 * "Article N(P)(L)" references and `"annex"` for "Annex I(2)(b)" ones —
 * the consumer dispatches on this to compose the right URL.
 *
 * `paragraph`, `letter`, `subparagraph` are the structured pin-cite
 * components. They are preserved as strings (the parser keeps them as
 * strings rather than ints to leave headroom for letter-suffixed
 * paragraphs e.g. "1a", and to mirror the JSON shape exactly).
 */
export interface InternalReference {
  raw: string;
  target_article: string;
  paragraph: string | null;
  letter: string | null;
  subparagraph: string | null;
  target_kind: 'article' | 'annex';
  location_in_source: ReferenceLocation;
}

/**
 * One external reference made FROM the article keyed in
 * `article_to_external_refs`. `kind` distinguishes GDPR (special-cased
 * because the AI Act has a sibling product at gdpr.annotated.nl) from any
 * other named EU instrument.
 *
 * `target_article` is null when the citation names the instrument as a
 * whole rather than a specific article inside it (e.g. "Regulation (EU)
 * 2022/2065" without "Article X of"). When non-null, the renderer can
 * deep-link to the GDPR site's per-article page or to EUR-Lex.
 *
 * `target_kind`:
 *   - "article"    — typical case ("Article 6 of Regulation (EU) 2016/679")
 *   - "instrument" — bare instrument citation, no article picked out
 */
export interface ExternalReference {
  raw: string;
  kind: 'external_gdpr' | 'external_other';
  target_article: string | null;
  paragraph: string | null;
  letter: string | null;
  subparagraph: string | null;
  celex: string | null;
  short_name: string | null;
  official_name: string | null;
  target_kind: 'article' | 'instrument';
  location_in_source: ReferenceLocation;
}

/**
 * Reverse-index entry: for the article keyed in `articles_referencing`,
 * each entry names a SOURCE article that cites it, with the pin-cite
 * (paragraph + letter) the source uses. Internal references only.
 */
export interface InternalReverseReference {
  raw: string;
  source_article: string;
  paragraph: string | null;
  letter: string | null;
}

// ─── Bilingual short-text helper ─────────────────────────────────────

export interface BilingualText {
  en: string;
  nl?: string | null;
}

// ─── Guidance (5.2) ──────────────────────────────────────────────────

export interface GuidanceDoc {
  canonical_id: string;
  source: 'commission' | 'ai_office' | 'edpb' | 'member_state' | 'other';
  document_type:
    | 'guideline'
    | 'opinion'
    | 'recommendation'
    | 'code_of_practice'
    | 'guide'
    | 'faq'
    | 'other';
  title: BilingualText;
  adoption_date: string;
  entry_into_force: string | null;
  end_of_validity: string | null;
  endorsement_status: 'endorsed' | 'historical' | null;
  supersedes: string | null;
  languages: Lang[];
  by_language: Record<string, GuidanceLanguageBlock>;
  url: string | BilingualText;
  body_paths: Record<Lang, string | null>;
  editorial_note: BilingualText | null;
}

export interface GuidanceLanguageBlock {
  page_count: number;
  paragraph_count: number;
  section_count: number;
  footnote_count: number;
  citations_found: number;
  source_file: string;
  source_file_checksum: string;
}

export interface GuidanceCitation {
  guidance_id: string;
  language: Lang;
  pin_cite: {
    raw: string;
    paragraph: number | string | null;
    letter: string | null;
    subparagraph: number | string | null;
  };
  location_in_doc: {
    section?: string;
    page?: number | null;
    footnote?: number | null;
    paragraph?: number | null;
  };
}
