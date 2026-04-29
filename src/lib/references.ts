/**
 * Reference rendering helpers (Step 4.9b, with split-wrap for ranges).
 *
 * The structured indexes produced by scripts/extract_article_references.py
 * give us, per source article, a list of internal + external references with
 * their original `raw` substrings (e.g. "Article 6(1)(f) of Regulation (EU)
 * 2016/679", "Articles 8 to 15"). This module wraps those substrings in
 * `<a>` tags inside an article's body text.
 *
 * URL composition:
 *
 *   internal article : /{lang}/articles/chapter-{N}/article-{NUM}/
 *   internal annex   : /{lang}/annexes/annex-{id_lower}/
 *   external_gdpr    : https://gdpr.annotated.nl/{lang}/article/{N}/
 *   external_other   : https://eur-lex.europa.eu/legal-content/{LANG}/TXT/?uri=CELEX:{celex}
 *
 * Whole-wrap vs split-wrap:
 *
 *   - SINGLE-target raws (e.g. "Article 6(1)", "Article 6(1) of Regulation
 *     (EU) 2016/679") wrap the entire raw substring as one anchor. The cite
 *     reads naturally and the user clicks anywhere on it to navigate.
 *
 *   - MULTI-target raws (ranges and coordinated lists, e.g. "Articles 8 to
 *     15", "Articles 5, 7 and 9", "Articles 102 to 109") wrap each
 *     article-number token individually. The connectors ("Articles", "to",
 *     "and", commas) stay unwrapped. Each endpoint becomes its own click
 *     target — matches how lawyers actually read these citations.
 *
 * Per handoff "Known gotchas":
 *   - External links carry target="_blank" rel="noopener" and a small ↗
 *     glyph so the reader sees they leave the site.
 *   - text_offset isn't recorded by the parser, so this module does its own
 *     substring search at render time. The match is exact: parser-level
 *     normalisation (the input is JSON post-4.3b) keeps the body text and
 *     the captured `raw` substring byte-identical.
 */

import type {
  Lang,
  InternalReference,
  ExternalReference,
} from '@/types/aiact';
import { getChapterForArticle } from './loader';

export function internalHref(lang: Lang, ref: InternalReference): string {
  if (ref.target_kind === 'annex') {
    return `/${lang}/annexes/annex-${ref.target_article.toLowerCase()}/`;
  }
  const chapter = getChapterForArticle(ref.target_article);
  if (chapter === null) return '#';
  return `/${lang}/articles/chapter-${chapter}/article-${ref.target_article}/`;
}

export function externalHref(lang: Lang, ref: ExternalReference): string {
  if (ref.kind === 'external_gdpr') {
    if (ref.target_article) {
      return `https://gdpr.annotated.nl/${lang}/article/${ref.target_article}/`;
    }
    return `https://gdpr.annotated.nl/${lang}/`;
  }
  const langUpper = lang.toUpperCase();
  return `https://eur-lex.europa.eu/legal-content/${langUpper}/TXT/?uri=CELEX:${ref.celex}`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

interface RefInfo {
  href: string;
  cls: string;
  external: boolean;
}

function buildAnchor(safe: string, info: RefInfo): string {
  if (info.external) {
    return (
      `<a class="${info.cls}" href="${info.href}" `
      + `target="_blank" rel="noopener">`
      + `${safe}<span class="ref-external-mark" aria-hidden="true"> ↗</span>`
      + `</a>`
    );
  }
  return `<a class="${info.cls}" href="${info.href}">${safe}</a>`;
}

/**
 * Pattern: digit run (with optional trailing letter) that's NOT inside a
 * pin-cite paren group. Lookbehind excludes "(" and other digits;
 * lookahead excludes ")" and other digits. Pin-cite digits like "(1)"
 * are protected because the open-paren guards them.
 */
const ARTICLE_TOKEN_RE = /(?<![(\d])\d+[a-z]?(?![\d)])/g;

/**
 * Roman-numeral token (for annex ranges like "Annexes I to III", though
 * none observed in the v1.1 corpus). Pattern requires uppercase letters
 * to avoid matching ordinary lowercase words.
 */
const ANNEX_TOKEN_RE = /(?<![(\w])[IVXLCDM]+(?![\w)])/g;

/**
 * Split-wrap: emit each article-number / annex-id substring inside `raw`
 * as its own anchor. Connectors ("Articles", "to", "and", commas) are
 * HTML-escaped and pass through unwrapped.
 */
function splitWrap(raw: string, refs: Array<{ target: string; info: RefInfo }>): string {
  const byTarget = new Map<string, RefInfo>();
  for (const r of refs) byTarget.set(r.target, r.info);

  // Decide which token regex to use based on whether the targets look
  // like article numbers (digits) or annex roman numerals.
  const sampleTarget = refs[0]?.target ?? '';
  const isAnnex = /^[IVXLCDM]+$/.test(sampleTarget);
  const tokenRe = isAnnex ? ANNEX_TOKEN_RE : ARTICLE_TOKEN_RE;
  // Reset lastIndex — the regex objects are module-level and stateful.
  tokenRe.lastIndex = 0;

  let result = '';
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = tokenRe.exec(raw)) !== null) {
    result += escapeHtml(raw.slice(lastIdx, m.index));
    const tok = m[0];
    const info = byTarget.get(tok);
    if (info) {
      result += buildAnchor(escapeHtml(tok), info);
    } else {
      result += escapeHtml(tok);
    }
    lastIdx = m.index + tok.length;
  }
  result += escapeHtml(raw.slice(lastIdx));
  return result;
}

/**
 * Wrap recognised reference substrings in an article's body text with
 * the appropriate `<a>` tags.
 *
 * Strategy: build one alternation regex over every unique `raw` string,
 * longest-first so "Article 5(1)(a)" wins over "Article 5". For each
 * matched raw, look up the entries: a single target → wrap whole; multi
 * targets → split-wrap each article number.
 */
export function wrapReferences(
  text: string,
  internalRefs: InternalReference[],
  externalRefs: ExternalReference[],
  lang: Lang,
): string {
  if (!text) return text;

  // Group by raw. Same raw may have multiple entries (ranges, coord lists).
  const internalGroups = new Map<string, InternalReference[]>();
  for (const r of internalRefs) {
    const list = internalGroups.get(r.raw);
    if (list) list.push(r);
    else internalGroups.set(r.raw, [r]);
  }
  const externalGroups = new Map<string, ExternalReference[]>();
  for (const r of externalRefs) {
    const list = externalGroups.get(r.raw);
    if (list) list.push(r);
    else externalGroups.set(r.raw, [r]);
  }

  type WholeEntry = { kind: 'whole'; info: RefInfo };
  type SplitEntry = { kind: 'split'; refs: Array<{ target: string; info: RefInfo }> };
  const lookup = new Map<string, WholeEntry | SplitEntry>();

  // Internal first. Split-wrap only when the raw resolves to MULTIPLE
  // DISTINCT targets — repeated identical references (same article cited
  // twice in one paragraph) stay whole-wrapped because they read as a
  // single citation that happens to appear more than once.
  for (const [raw, refs] of internalGroups) {
    const distinctTargets = new Set(refs.map((r) => r.target_article));
    if (distinctTargets.size === 1) {
      const r = refs[0];
      const info: RefInfo = {
        href: internalHref(lang, r),
        cls: r.target_kind === 'annex'
          ? 'article-ref article-ref-internal article-ref-annex'
          : 'article-ref article-ref-internal',
        external: false,
      };
      lookup.set(raw, { kind: 'whole', info });
    } else {
      const split = refs.map((r) => ({
        target: r.target_article,
        info: {
          href: internalHref(lang, r),
          cls: r.target_kind === 'annex'
            ? 'article-ref article-ref-internal article-ref-annex'
            : 'article-ref article-ref-internal',
          external: false,
        } as RefInfo,
      }));
      lookup.set(raw, { kind: 'split', refs: split });
    }
  }
  // External overrides — same raw with external classification beats internal.
  // Same distinct-target rule applies.
  for (const [raw, refs] of externalGroups) {
    const distinctTargets = new Set(refs.map((r) => r.target_article ?? ''));
    if (distinctTargets.size === 1) {
      const r = refs[0];
      const info: RefInfo = {
        href: externalHref(lang, r),
        cls: r.kind === 'external_gdpr'
          ? 'article-ref article-ref-gdpr'
          : 'article-ref article-ref-external',
        external: true,
      };
      lookup.set(raw, { kind: 'whole', info });
    } else {
      const split = refs.map((r) => ({
        target: r.target_article ?? '',
        info: {
          href: externalHref(lang, r),
          cls: r.kind === 'external_gdpr'
            ? 'article-ref article-ref-gdpr'
            : 'article-ref article-ref-external',
          external: true,
        } as RefInfo,
      }));
      lookup.set(raw, { kind: 'split', refs: split });
    }
  }


  if (lookup.size === 0) return text;

  // Sort longest-first to prevent "Article 5" matching inside "Article 5(1)(a)".
  const raws = [...lookup.keys()].sort((a, b) => b.length - a.length);
  const pattern = new RegExp(raws.map(escapeRegex).join('|'), 'g');

  return text.replace(pattern, (match) => {
    const entry = lookup.get(match);
    if (!entry) return match;
    if (entry.kind === 'whole') {
      return buildAnchor(escapeHtml(match), entry.info);
    }
    return splitWrap(match, entry.refs);
  });
}
