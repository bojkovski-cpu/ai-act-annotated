/**
 * AI Act locale registry — Phase 3 (Option 1+ per step-3.1 § 7.1).
 *
 * The AI Act ships in English (canonical) and Dutch. This file is the
 * source-of-truth list of locales the AI Act renders, with each locale's
 * fallback policy and canonical-language flag.
 *
 * In Phase 4, the family-wide `InstrumentConfig` registry will carry a
 * `locales: LocaleInfo[]` field per instrument; this constant is the
 * AI-Act-specific list that Phase 4's InstrumentConfig will absorb.
 *
 * Adding a third locale (French, German, etc.) is one entry here + one
 * new content JSON file per affected entity type + a content workstream
 * to populate the strings. No type-system change needed because `Locale`
 * is an open string per step-3.1 § 7.1.
 *
 * Reference:
 *   control-room/reference/design-bundle/step-3.1-unified-interface-spec.html
 *   § 7.1 (locale plurality)
 */
import type { LocaleInfo } from '@/types/aiact';

export const AIACT_LOCALES: LocaleInfo[] = [
  {
    code: 'en',
    name: 'English',
    isCanonical: true,
    // canonical locale has no fallback
  },
  {
    code: 'nl',
    name: 'Nederlands',
    isCanonical: false,
    fallback: 'en',
  },
];

/** Convenience: the canonical locale's code. AI Act = 'en'. */
export const CANONICAL_LOCALE = AIACT_LOCALES.find((l) => l.isCanonical)!.code;

/** Convenience: the set of valid locale codes for runtime validation. */
export const VALID_LOCALES: ReadonlySet<string> = new Set(AIACT_LOCALES.map((l) => l.code));

/** Look up a LocaleInfo by code. Returns undefined for unknown codes. */
export function getLocaleInfo(code: string): LocaleInfo | undefined {
  return AIACT_LOCALES.find((l) => l.code === code);
}

/**
 * Pick the best string from a LocalizedText for the given locale, following
 * the fallback chain. Returns undefined if no locale in the chain has a value.
 *
 *   const title = pickLocalized({ en: 'Hi', nl: 'Hallo' }, 'nl');  // 'Hallo'
 *   const title = pickLocalized({ en: 'Hi' }, 'nl');               // 'Hi' (NL falls back to EN)
 *   const title = pickLocalized({}, 'nl');                          // undefined
 */
export function pickLocalized(
  text: Partial<Record<string, string>>,
  locale: string,
): string | undefined {
  const visited = new Set<string>();
  let cur: string | undefined = locale;
  while (cur && !visited.has(cur)) {
    visited.add(cur);
    if (text[cur]) return text[cur];
    cur = getLocaleInfo(cur)?.fallback;
  }
  // Final fallback: try the canonical locale directly.
  return text[CANONICAL_LOCALE];
}
