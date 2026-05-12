/**
 * Annotated.nl — build-time feature flags.
 *
 * Loads `flags.json` from the repo root and validates the dependency
 * chain before any page is rendered. An illegal combination fails the
 * Astro build instead of producing a half-migrated site.
 *
 * Workflow: flag flips are pull requests. Merging a PR is the cutover.
 * No runtime overrides, no per-user flags, no third-party SDK.
 *
 * See handoff/INDEX.md § "Feature-flag system" for the full rationale.
 */

import raw from '../flags.json' assert { type: 'json' };

export type FlagName =
  | 'FF_CANONICAL_IDS'
  | 'FF_UNIFIED_REFERENCES'
  | 'FF_BILINGUAL_PINCITE'
  | 'FF_NEW_ENTITY_TYPES'
  | 'FF_CONVERGENT_COMPONENTS'
  | 'FF_AMENDMENT_SURFACE';

export type FlagMap = Record<FlagName, boolean>;

/**
 * Dependency chain — a flag may only be `true` if every flag it requires
 * is also `true`. Mirrors the phase ordering in Step 3.3 § D.
 */
const REQUIRES: Record<FlagName, FlagName[]> = {
  FF_CANONICAL_IDS:         [],
  FF_UNIFIED_REFERENCES:    ['FF_CANONICAL_IDS'],
  FF_BILINGUAL_PINCITE:     ['FF_CANONICAL_IDS'],
  FF_NEW_ENTITY_TYPES:      ['FF_CANONICAL_IDS', 'FF_BILINGUAL_PINCITE'],
  FF_CONVERGENT_COMPONENTS: ['FF_UNIFIED_REFERENCES', 'FF_BILINGUAL_PINCITE'],
  FF_AMENDMENT_SURFACE:     ['FF_NEW_ENTITY_TYPES', 'FF_CONVERGENT_COMPONENTS'],
};

export class FlagValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FlagValidationError';
  }
}

export function validate(map: FlagMap): void {
  const errors: string[] = [];

  for (const [flag, deps] of Object.entries(REQUIRES) as [FlagName, FlagName[]][]) {
    if (map[flag]) {
      const missing = deps.filter(d => !map[d]);
      if (missing.length > 0) {
        errors.push(
          `  • ${flag} is enabled but requires: ${missing.join(', ')}`,
        );
      }
    }
  }

  // Catch typos / unknown keys.
  const known = new Set(Object.keys(REQUIRES));
  for (const key of Object.keys(map)) {
    if (!known.has(key)) {
      errors.push(`  • Unknown flag in flags.json: ${key}`);
    }
  }

  if (errors.length > 0) {
    throw new FlagValidationError(
      `flags.json is in an illegal state:\n${errors.join('\n')}`,
    );
  }
}

validate(raw as FlagMap);

export const flags: Readonly<FlagMap> = Object.freeze(raw as FlagMap);
