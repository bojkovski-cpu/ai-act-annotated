/**
 * Tests for the feature-flag validator.
 *
 * Runs with vitest. Co-locates with src/flags.ts.
 */

import { describe, it, expect } from 'vitest';
import { validate, FlagValidationError, type FlagMap } from './flags';

const allFalse = (): FlagMap => ({
  FF_CANONICAL_IDS:         false,
  FF_UNIFIED_REFERENCES:    false,
  FF_BILINGUAL_PINCITE:     false,
  FF_NEW_ENTITY_TYPES:      false,
  FF_CONVERGENT_COMPONENTS: false,
  FF_AMENDMENT_SURFACE:     false,
});

describe('feature-flag validator', () => {
  it('accepts all-false', () => {
    expect(() => validate(allFalse())).not.toThrow();
  });

  it('accepts FF_CANONICAL_IDS alone (Phase 1 cutover)', () => {
    const m = allFalse();
    m.FF_CANONICAL_IDS = true;
    expect(() => validate(m)).not.toThrow();
  });

  it('rejects FF_UNIFIED_REFERENCES without FF_CANONICAL_IDS', () => {
    const m = allFalse();
    m.FF_UNIFIED_REFERENCES = true;
    expect(() => validate(m)).toThrow(FlagValidationError);
  });

  it('rejects FF_CONVERGENT_COMPONENTS without its full dep chain', () => {
    const m = allFalse();
    m.FF_CANONICAL_IDS = true;
    m.FF_CONVERGENT_COMPONENTS = true; // missing UNIFIED_REFERENCES + BILINGUAL_PINCITE
    expect(() => validate(m)).toThrow(/FF_UNIFIED_REFERENCES, FF_BILINGUAL_PINCITE/);
  });

  it('accepts full Phase 6 stack', () => {
    const m: FlagMap = {
      FF_CANONICAL_IDS:         true,
      FF_UNIFIED_REFERENCES:    true,
      FF_BILINGUAL_PINCITE:     true,
      FF_NEW_ENTITY_TYPES:      true,
      FF_CONVERGENT_COMPONENTS: true,
      FF_AMENDMENT_SURFACE:     true,
    };
    expect(() => validate(m)).not.toThrow();
  });

  it('rejects unknown keys', () => {
    const m = allFalse() as FlagMap & Record<string, boolean>;
    m.FF_NOT_A_REAL_FLAG = true;
    expect(() => validate(m as FlagMap)).toThrow(/Unknown flag/);
  });
});
