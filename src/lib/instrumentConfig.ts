/**
 * InstrumentConfig — per-instrument editorial knobs for the
 * supplementary surface.
 *
 * Phase 5.5d (2026-05-12) introduces this file with the tooltip
 * copy locked at OQ-10. The shape is the contract that AI Act, GDPR,
 * DSA, and NIS2 will all consume — same components, different copy.
 * Step 3.1 § 7.2 of the design bundle is the eventual home for the
 * full InstrumentConfig schema (categoriesEnabled, dpaRegistry,
 * predecessorInstrument, autoMirrorReferences, locale rules, etc.);
 * Phase 5.5d ships only the tooltip slice.
 *
 * Editorial principle (OQ-10): copy is locked at the instrument level,
 * not per-article. The same tooltip text appears under the History tab
 * on Article 6 as on Article 99. Per-article variation would be
 * editorial sand to chase.
 *
 * AI Act specifics:
 *   - Guidance copy substitutes "EU AI Office" for "EDPB / WP29"
 *     (the AI Act's standing-bodies analogue).
 *   - History copy drops the predecessor-instrument framing — the AI
 *     Act has no predecessor instrument.
 *   - Decisions tab not yet populated; tooltip wording uses
 *     "supervisory authority" terminology that survives the GDPR-era
 *     `dpa` species being renamed to `sa` in the unified schema.
 *   - speciesTooltips includes keys for the chip slugs the Research
 *     panel renders today (all + the categories), plus reserved keys
 *     for the species that light up under Decisions in the future
 *     (`court`, `sa`).
 */
export interface InstrumentConfig {
  /** Tooltip text on Browse-mode tabs. Keyed by category slug
   *  (history, implementation, recitals, decisions, guidance). */
  categoryTooltips: Record<string, string>;
  /** Tooltip text on Research-mode chips. Includes 'all' plus the
   *  category slugs that surface as chips today. Reserved keys for
   *  intra-tab species (court, sa) light up when Decisions data
   *  arrives. */
  speciesTooltips: Record<string, string>;
}

export const aiActInstrumentConfig: InstrumentConfig = {
  categoryTooltips: {
    history:
      'Drafting trail of this provision through Commission, Council, Parliament, and the trilogue.',
    implementation:
      'National transposition acts and member-state law operationalising this provision.',
    recitals:
      'Recitals of Regulation (EU) 2024/1689 that cite or contextualise this article.',
    decisions:
      'Court judgements and supervisory-authority enforcement orders applying this provision.',
    guidance:
      'Soft-law output from the EU AI Office, the Commission, and national supervisory authorities.',
  },
  speciesTooltips: {
    all: 'All annotations across categories.',
    history: 'Drafting stages of this provision — Commission, Council, Parliament, trilogue, final.',
    recitals: 'Recitals of Regulation (EU) 2024/1689 referencing this article.',
    guidance: 'Guidance documents citing this article.',
    // Reserved for Decisions when content lands:
    court: 'Judgements from courts — CJEU, national courts, arbitration.',
    sa: 'Enforcement orders from national supervisory authorities.',
  },
};
