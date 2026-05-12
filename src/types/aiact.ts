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
 * Phase 1 (2026-05-12, Path A schema-first migration) introduces canonical_id
 * and version_id on Article / Recital / Annex. Backfilled in src/data/*.json
 * by scripts/migrate_canonical_ids.py with version_id = '2024-08-01' (regulation
 * entry into force). Annex points decomposed into structured AnnexPoint records
 * for Pattern A annexes per annex-point-grain-aiact-2026-05-12.md.
 *
 * Phase 2 (2026-05-12) adds the unified Reference / PinCite / InstrumentId
 * types per step-3.3 § C. The legacy cross_references.json (5 junction maps)
 * stays in place; scripts/migrate_unified_references.py emits a new
 * src/data/references.json as Reference[] derived from the legacy maps.
 * FF_UNIFIED_REFERENCES gates which shape the loader exposes.
 *
 * Phase 3 (2026-05-12, Option 1+ per step-3.1 § 7.1) introduces locale
 * plurality: open `Locale` type, `LocaleInfo` registry interface, and
 * `LocalizedText` = Partial<Record<Locale, string>>. The closed `Lang =
 * 'en' | 'nl'` stays as a backward-compat alias for the current AI Act
 * locale set; new entity types in Phase 4 (CourtJudgement, SADecision,
 * ImplementingLaw) use LocalizedText from day one. Existing per-language
 * file storage (articles_en.json + articles_nl.json + …) is unchanged.
 *
 * Phase 4 (2026-05-12) adds new entity types per step-3.2 § B/§C/§A.3 and
 * step-3.3 § C: CourtJudgement, SADecision (renamed from DPADecision per
 * step-3.3 § C edge note — AI Act has supervisory authorities / MSAs,
 * not DPAs), ImplementingLaw, AmendmentInstrument, AmendmentCallout.
 * Empty JSON stubs in src/data/{court_judgements,sa_decisions,
 * implementing_law}.json; AmendmentInstrument + AmendmentCallout
 * populated from omnibus_amendments_en.json via
 * scripts/migrate_amendment_instruments.py. FF_NEW_ENTITY_TYPES gates
 * which components consume the new schemas.
 *
 * Number normalisation: all entity numbers (article.number, recital.number,
 * paragraph.number) are STRINGS at the data layer. EN data was numeric in
 * the legacy ai_act_structured.json blob; the bridge scripts normalise to
 * string for symmetry with the NL corpus and to leave headroom for letter-
 * suffixed numbers (e.g. Omnibus's new Article 4a / 60a, when those land).
 */

/**
 * Locale identifier — the open form. Runtime-validates against the
 * instrument's declared locale list (see AIACT_LOCALES in src/lib/locales.ts;
 * generalises to InstrumentConfig.locales in Phase 4).
 *
 * Open string for forward-compatibility per step-3.1 § 7.1: every new
 * locale lands by editing the registry, not the type system.
 */
export type Locale = string;

/**
 * Per-locale metadata in an instrument's locale registry.
 *
 *   `isCanonical`  — exactly one locale per instrument is canonical (the
 *                    source-of-truth language; usually the language the
 *                    instrument was originally drafted in).
 *   `fallback`     — locale to fall back to when a field is missing in this
 *                    locale (e.g. NL fields fall back to EN). The canonical
 *                    locale typically has no fallback.
 */
export interface LocaleInfo {
  code: Locale;
  name: string;
  isCanonical: boolean;
  fallback?: Locale;
}

/**
 * Open-locale text shape replacing the closed `BilingualText { en; nl? }`
 * for new entity types. Keys are Locale codes; values are the localised
 * string. Missing locales fall back per `LocaleInfo.fallback`, then to the
 * canonical locale.
 *
 *   { en: "Lawfulness…", nl: "Rechtmatigheid…", fr: "Licéité…" }
 *
 * Phase 4 entity types (CourtJudgement, SADecision, ImplementingLaw, etc.)
 * use this from day one. Existing entities (Article, Recital, Annex) keep
 * the per-language-file storage architecture.
 */
export type LocalizedText = Partial<Record<Locale, string>>;

/**
 * Closed locale union for the AI Act's current state (English + Dutch).
 * Kept as a backward-compat alias for `Locale`; existing consumers don't
 * change. New consumers that want to be locale-list-agnostic should type
 * against `Locale` directly.
 */
export type Lang = 'en' | 'nl';

// ─── Canonical identifiers (Phase 1) ─────────────────────────────────

/**
 * Stable, version-independent identifier for any entity in the Annotated.nl
 * family. Format: `{instrument}/{kind}/{number}` — e.g. `aiact/art/6`,
 * `aiact/rec/47`, `aiact/annex/iii`, `aiact/annex/iii/3`, `aiact/annex/iii/3/a`,
 * `aiact/chapter/ii`. Lowercase throughout. Roman numerals lowercase for
 * annex + chapter identifiers (`iii`, not `III`). Cross-instrument refs use
 * the target instrument's slug (`gdpr/art/6`, `dsa/art/14`).
 *
 * See control-room/reference/url-contract-aiact-2026-05-12.md for the URL-shape
 * derivation rule and the redirect map from legacy paths.
 */
export type CanonicalId = string;

/**
 * The version of an entity in the unified schema. Phase 1 backfills every
 * record with the regulation's entry-into-force date (`2024-08-01` for the
 * AI Act). Phase 6 introduces forward-dated versions for forthcoming Omnibus
 * amendments; until then there is exactly one version per entity.
 */
export type VersionId = string;

/**
 * Instrument identifier — the slug segment of a CanonicalId. Phase 2 known
 * values are `'aiact'` and `'gdpr'`. Future instruments (DSA, NIS2, DORA, etc.)
 * add their own slugs as they onboard the registry. External EU instruments
 * that aren't in the registry are identified by their CELEX number directly
 * (e.g. `'32016L0680'` for Directive (EU) 2016/680).
 *
 * Open string for forward-compatibility — the registry validates at build time.
 */
export type InstrumentId = string;

/**
 * Pin-cite into an entity. Paragraph + letter are the common grain in legal
 * citations ("Article 6(1)(a)"); subparagraph + sentence cover sub-letter
 * specificity; annex + annexPoint exist for AI Act references to annexes
 * with structured points (Annex III(3)(a)).
 *
 * All fields optional — a bare {} represents an instrument-level citation.
 */
export interface PinCite {
  article?: string;
  paragraph?: string;
  letter?: string;
  subparagraph?: string;
  sentence?: number;
  annex?: string;
  annexPoint?: string;
}

/**
 * One reference edge in the unified table per step-3.3 § C. Replaces the
 * four `article_to_*` junction maps in the legacy cross_references.json.
 *
 * `source` and `target` are canonical_ids; for known-registry instruments
 * (`aiact`, `gdpr`) they follow `{instrument}/{kind}/{number}`. For external
 * EU instruments without a registry entry, the canonical_id form uses the
 * target instrument's CELEX as the slug, e.g. `32016L0680/art/4`.
 *
 * `sourcePin` is always present (the parser knows where in the source the
 * citation appears). `targetPin` is present only when the citation pin-cites
 * a specific point inside the target.
 *
 * `kind` is always `'cite'` at v1; the unified schema reserves `'replaces'`,
 * `'implements'`, `'interprets'` for later phases (predecessor/transposition
 * relationships, judicial interpretations, etc.).
 *
 * `id` is a stable deterministic hash of source + sourcePin + target +
 * targetPin + kind, used as a primary key when the inverse-lookup index is
 * built at build time.
 */
export interface Reference {
  id: string;
  source: CanonicalId;
  sourcePin: PinCite;
  target: CanonicalId | string;
  targetPin?: PinCite;
  kind: 'cite' | 'replaces' | 'implements' | 'interprets';
  sourceInstrument: InstrumentId;
  targetInstrument: InstrumentId;
}

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
  /** `aiact/art/{number}`. Stable, version-independent identifier. Phase 1. */
  canonical_id: CanonicalId;
  /** ISO date of the version's entry into force. Phase 1 backfill: '2024-08-01'. */
  version_id: VersionId;
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
  /** `aiact/rec/{number}`. Phase 1. */
  canonical_id: CanonicalId;
  /** ISO date of the version's entry into force. Phase 1 backfill: '2024-08-01'. */
  version_id: VersionId;
  number: string;
  text: string;
}

// ─── Annex ────────────────────────────────────────────────────────────

/**
 * One letter sub-point under a numbered point in a Pattern A annex with letter
 * sub-points (Annex III, IV, X, XII per annex-point-grain-aiact-2026-05-12.md).
 * Emitted by scripts/migrate_canonical_ids.py from the source text; not present
 * before Phase 1. Sub-letters get their own canonical IDs (Option canonical,
 * decided 2026-05-12) so cross-references at letter grain are URL-addressable.
 */
export interface AnnexLetter {
  /** `aiact/annex/{roman}/{point}/{letter}`. Lowercase letter. */
  canonical_id: CanonicalId;
  /** Single lowercase letter, e.g. 'a', 'b'. */
  letter: string;
  /** Body text of this letter. */
  text: string;
}

/**
 * One top-level structural unit inside an annex — a numbered point in Pattern A
 * annexes with numeric enumeration (III, IV, V, VI, VII, IX, X, XII), or a
 * lettered point in Pattern A annexes with letter-only enumeration (XIII).
 *
 * `points: []` for Pattern B annexes (I, VIII, XI — sectioned, deferred to
 * Phase 4) and Pattern C annexes (II — no list structure).
 */
export interface AnnexPoint {
  /** `aiact/annex/{roman}/{position}`. */
  canonical_id: CanonicalId;
  /** Top-level enumeration as it appears in the source. Numeric for most
   *  Pattern A annexes (`'1'`, `'2'`, …); lowercase letter for Annex XIII
   *  (`'a'`, `'b'`, …). String to allow both shapes. */
  position: string;
  /** Body text of this point (excluding sub-letters when those exist as
   *  structured `letters` rows). */
  body: string;
  /** Letter sub-points under this numbered point, when the annex has them
   *  (Annex III / IV / X / XII). Empty array when the point is flat. */
  letters: AnnexLetter[];
}

export interface Annex {
  /** `aiact/annex/{id.toLowerCase()}`. Phase 1. */
  canonical_id: CanonicalId;
  /** ISO date of the version's entry into force. Phase 1 backfill: '2024-08-01'. */
  version_id: VersionId;
  /** Roman-numeral identifier, e.g. "I", "II", "XIII". Preserved as-uppercased
   *  for backward compatibility with existing renderers. */
  id: string;
  title: string;
  text: string;
  /** Top-level structural points. Populated for Pattern A annexes (III, IV,
   *  V, VI, VII, IX, X, XII, XIII); empty for Pattern B (I, VIII, XI) and
   *  Pattern C (II) until Phase 4. See annex-point-grain-aiact-2026-05-12.md. */
  points: AnnexPoint[];
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
  // Doc-internal chapter outline per language, populated by build_guidance.py
  // from the parsed body's `## N. …` headings (skipping Frontmatter/Footnotes).
  // Drives the doc-specific left-sidebar nav on /{lang}/guidance/<slug>/.
  chapters?: Record<Lang, Array<{ title: string; anchor: string }>>;
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


// ─── Phase 4 — new entity types ─────────────────────────────────────
//
// Per step-3.2 § B/§C/§A.3 and step-3.3 § C: CourtJudgement, SADecision,
// ImplementingLaw, AmendmentInstrument, AmendmentCallout.
//
// AI Act note: the supervisory body is the AI Office + national market-
// surveillance authorities (MSAs), not data-protection authorities.
// step-3.3 § C renames DPADecisionRow → SADecisionRow ("Supervisory
// Authority") for the unified family; the shape is identical.

/** ISO 3166-1 alpha-2 country code; 'EU' for CJEU + EGC. */
export type ISO3166Alpha2 = string;

/** ISO 8601 date string, YYYY-MM-DD. */
export type ISODate = string;

/** Court level taxonomy per step-3.2 § B.3. */
export type CourtLevel = 'CJEU' | 'EGC' | 'national' | 'arbitral';

/**
 * Per-instrument court registry entry. Mirrors the per-instrument MSA
 * registry pattern (OQ-C.1). Phase 4 ships a placeholder list; content
 * ops populates as court cases on AI Act emerge.
 */
export interface Court {
  /** Stable slug, e.g. 'cjeu', 'bverwg-de', 'rb-den-haag'. */
  canonicalId: string;
  shortName: LocalizedText;
  level: CourtLevel;
}

/**
 * CURIA-aligned outcome vocabulary per OQ-B.1. Phase 4 ships the broad
 * five-state placeholder; the data pipeline will map to CURIA terms when
 * the first case lands. National-court rows map to the nearest CURIA-
 * equivalent term.
 */
export type CourtOutcome =
  | 'judgement'
  | 'order'
  | 'opinion'
  | 'view'
  | 'pending';

/**
 * One court judgement applying or interpreting AI Act articles. Step-3.2
 * § B.3. Phase 4 schema is empty (no AI Act case law yet); content ops
 * fills as preliminary references and national rulings arrive.
 */
export interface CourtJudgement {
  id: string;
  ecli: string;
  court: Court;
  jurisdiction: ISO3166Alpha2;
  date: ISODate;
  /** Anonymised parties per source convention. */
  parties: string;
  caseNumber: string;
  outcome: CourtOutcome;
  /** ISO 639-1 of the authentic text. */
  language: string;
  pinCites: PinCite[];
  /** 1-2 sentence editorial summary. */
  holdingSnippet: LocalizedText;
  /** Verbatim quote, Research mode only. */
  holdingExtract?: LocalizedText;
  /** Canonical case-law page URL (cross-article aggregation). */
  fullCasePageUrl?: string;
}

/**
 * Per-instrument supervisory-authority registry entry. AI Act = national
 * market-surveillance authorities (MSAs) + the AI Office. The
 * `canonicalId` is the slug used in SADecision.authority.canonicalId.
 *
 * OQ-C.1: flat lookup table per instrument; no central registry.
 */
export interface SupervisoryAuthority {
  canonicalId: string;
  acronym: string;
  fullName: LocalizedText;
  country: ISO3166Alpha2;
}

/**
 * Remedy taxonomy for an SADecision. Combined = fine + order.
 */
export type SARemedy =
  | 'fine'
  | 'warning'
  | 'order-to-comply'
  | 'order-to-cease'
  | 'processing-ban'
  | 'no-action'
  | 'combined';

/**
 * Monetary fine amount in a SADecision.
 */
export interface SAFine {
  amount: number;
  currency: string;
}

/**
 * Appeal disposition (v0 placeholder per OQ-C.2). The expanded schema
 * (substantive appeal chain + parallel interim-measures procedure) is
 * deferred to a follow-on schema-design session.
 */
export interface SAAppealOutcome {
  status: 'upheld' | 'reduced' | 'overturned' | 'pending';
  modifiedFine?: SAFine;
  /** ECLI of the appeal court judgement, if one exists. Cross-link to a
   *  CourtJudgement row. */
  appealCaseEcli?: string;
  appealDate?: ISODate;
}

/**
 * One supervisory-authority enforcement decision. Step-3.2 § C.4 (renamed
 * from DPADecision per step-3.3 § C). Phase 4 schema is empty; content
 * ops fills when MSAs start enforcing the AI Act (2026+).
 *
 * Schema version note: `schemaVersion: '0.1'` flags this as the v0
 * placeholder per Risk H.5 in step-3.3. When OQ-C.2 resolves (expanded
 * appeal model), records bump to v0.2 and the `appealOutcome` field
 * generalises to an appeal chain + parallel interim-measures track.
 */
export interface SADecision {
  id: string;
  schemaVersion: '0.1';
  decisionNumber: string;
  authority: SupervisoryAuthority;
  country: ISO3166Alpha2;
  date: ISODate;
  /** The regulated entity, not the complainant. */
  controller: string;
  remedy: SARemedy;
  fine?: SAFine;
  appealOutcome?: SAAppealOutcome;
  pinCites: PinCite[];
  holdingSnippet: LocalizedText;
  /** ISO 639-1 of the authentic text. */
  language: string;
  fullDecisionPageUrl?: string;
}

/**
 * Citation to a Member-State implementing or transposing instrument that
 * operationalises an AI Act provision. Phase 4 schema is empty; AI Act
 * Member-State implementing acts start arriving 2026+ (Art. 70
 * designations).
 *
 * Schema sourced from step-3.0 inventory DAT-11 (provisional).
 */
export interface ImplementingLaw {
  id: string;
  jurisdiction: ISO3166Alpha2;
  /** Short citation form, e.g. 'UAVG' (Dutch GDPR transposition shorthand). */
  instrumentShort: string;
  /** Full official title. */
  instrumentFull: LocalizedText;
  /** The article number within the implementing instrument. */
  article: string;
  /** Verbatim body of the implementing-article text, where available. */
  body?: LocalizedText;
  url?: string;
}

/**
 * Top-level amendment instrument — an EU regulation or directive that
 * amends the AI Act. Phase 4 migrates the existing AI Omnibus
 * (COM(2025) 836) into this shape.
 *
 * Step-3.3 § C.
 *
 *   kind: 'omnibus' — broad multi-provision package, like COM(2025) 836
 *   kind: 'targeted' — narrow single-issue amendment
 *   kind: 'corrigendum' — drafting fix from the EU institutions
 */
export type AmendmentInstrumentKind = 'omnibus' | 'targeted' | 'corrigendum';
export type AmendmentInstrumentStatus = 'proposed' | 'adopted-not-in-force' | 'in-force';

export interface AmendmentInstrument {
  canonicalId: CanonicalId;
  kind: AmendmentInstrumentKind;
  shortTitle: LocalizedText;
  /** Long official title, optional. */
  longTitle?: LocalizedText;
  /** Provenance label, e.g. 'COM(2025) 836 final'. */
  sourceLabel?: string;
  status: AmendmentInstrumentStatus;
  adoptedDate?: ISODate;
  entryIntoForceDate?: ISODate;
  /** Canonical IDs of every article / annex this instrument amends. */
  affects: CanonicalId[];
}

/**
 * Per-paragraph amendment as it renders inline on the article page.
 * Step-3.2 § A. Phase 4 migrates the 29 omnibus records into this shape;
 * Phase 6 lights up the inline AmendmentCallout component that renders
 * them.
 *
 * Status lifecycle (OQ-A.2):
 *   proposed | adopted-not-in-force — inline callout + "Amendment history" appendix
 *   in-force-current   — body shows new text, callout cites the previous
 *                        wording (transitional handoff)
 *   in-force-superseded — historical, lives in the History tab as a
 *                          `superseded-version` species
 *
 * Redline kinds (OQ-A.2):
 *   replace → both oldText and newText
 *   insert  → only newText
 *   delete  → only oldText
 *
 * For the AI Omnibus initial migration, `redline.oldText` and
 * `redline.newText` are mostly undefined — only the `summary` was
 * captured by the original parser. Phase 4 ships the structural records
 * with summary as a fallback; content ops fills oldText/newText later.
 */
export type AmendmentCalloutStatus =
  | 'proposed'
  | 'adopted-not-in-force'
  | 'in-force-current'
  | 'in-force-superseded';

export type AmendmentRedlineKind = 'replace' | 'insert' | 'delete';

export interface AmendmentRedline {
  kind: AmendmentRedlineKind;
  oldText?: LocalizedText;
  newText?: LocalizedText;
  /** Fallback editorial summary when oldText/newText aren't captured. */
  summary?: LocalizedText;
}

export interface AmendmentCallout {
  id: string;
  /** Article being amended. */
  affectedArticle: CanonicalId;
  /** Paragraph id within the article, e.g. '1', '2'. */
  affectedParagraphId: string;
  /** Sub-provision (point, letter, sentence) within the paragraph. */
  affectedSubparagraphId?: string;
  status: AmendmentCalloutStatus;
  effectiveDate?: ISODate;
  adoptedDate?: ISODate;
  redline: AmendmentRedline;
  /** Reference to the AmendmentInstrument this callout belongs to. */
  amendingInstrument: {
    canonicalId: CanonicalId;
    shortTitle: LocalizedText;
    /** Article of the amending instrument that makes the change,
     *  e.g. 'Art. 14' of the Omnibus. */
    sourceArticle?: string;
  };
}
