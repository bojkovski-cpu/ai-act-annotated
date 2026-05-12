#!/usr/bin/env python3
"""
Phase 2 — unified references migration.

Reads src/data/cross_references.json (legacy 5-map junction structure) and
emits src/data/references.json as a flat Reference[] per the unified schema
in src/types/aiact.ts (Reference, PinCite, InstrumentId).

Migration direction (forward edges only — reverse indexes are derived at
build time from the unified structure):
  * article_to_articles_internal   -> forward (article|annex target)
  * article_to_recitals             -> forward (article -> recital)
  * article_to_external_refs        -> forward (article -> external)

Skipped (derived):
  * recital_to_articles    — reverse of article_to_recitals
  * articles_referencing   — reverse of article_to_articles_internal

External target canonical_ids:
  * external_gdpr with target_article=N  -> gdpr/art/N (targetInstrument=gdpr)
  * external_gdpr without target_article -> gdpr (instrument-level)
  * external_other with CELEX+target_art -> {CELEX}/art/N (targetInstrument=CELEX)
  * external_other with CELEX only       -> {CELEX} (instrument-level)
  * external_other without CELEX         -> raw text fallback (preserved verbatim)

Idempotent: same input -> same output, byte-identical.

Usage:
    python3 scripts/migrate_unified_references.py [--dry-run] [--verbose]

References:
    src/types/aiact.ts (Reference, PinCite, InstrumentId)
    control-room/reference/design-bundle/step-3.3-aiact-schema-migration.html §C
    control-room/reference/design-bundle/INDEX.md (locked decisions)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "src" / "data"

SOURCE_FILE = DATA_DIR / "cross_references.json"
DEST_FILE = DATA_DIR / "references.json"


def make_pincite(paragraph: str | None = None,
                 letter: str | None = None,
                 subparagraph: str | None = None,
                 article: str | None = None,
                 annex: str | None = None,
                 annex_point: str | None = None) -> dict:
    """Build a PinCite dict, omitting None/empty fields.

    Empty PinCite (no pin info) → empty dict {}.
    """
    pc: dict[str, Any] = {}
    if article:
        pc["article"] = article
    if paragraph and paragraph != "None":
        pc["paragraph"] = str(paragraph)
    if letter:
        pc["letter"] = letter
    if subparagraph:
        pc["subparagraph"] = subparagraph
    if annex:
        pc["annex"] = annex
    if annex_point:
        pc["annexPoint"] = annex_point
    return pc


def derive_id(source: str, source_pin: dict, target: str, target_pin: dict | None, kind: str) -> str:
    """Stable hash of (source, sourcePin, target, targetPin, kind)."""
    blob = json.dumps(
        {"s": source, "sp": source_pin, "t": target, "tp": target_pin or {}, "k": kind},
        sort_keys=True, ensure_ascii=False,
    )
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return h[:16]


def emit_reference(*, source: str, source_pin: dict, target: str, target_pin: dict | None,
                   kind: str, source_instrument: str, target_instrument: str) -> dict:
    """Build a Reference dict matching the TS interface."""
    ref: dict[str, Any] = {
        "id": derive_id(source, source_pin, target, target_pin, kind),
        "source": source,
        "sourcePin": source_pin,
        "target": target,
        "kind": kind,
        "sourceInstrument": source_instrument,
        "targetInstrument": target_instrument,
    }
    if target_pin:
        ref["targetPin"] = target_pin
    return ref


# ─── Source-specific migrators ───────────────────────────────────


def migrate_article_to_articles_internal(cr: dict) -> list[dict]:
    """article_to_articles_internal → forward Reference[] (article→article|annex)."""
    out = []
    table = cr.get("article_to_articles_internal", {}) or {}
    for source_article, refs in table.items():
        for ref in refs:
            loc = ref.get("location_in_source") or {}
            source_pin = make_pincite(paragraph=loc.get("paragraph"), letter=loc.get("letter"))

            tk = ref.get("target_kind")
            if tk == "annex":
                target = f"aiact/annex/{ref['target_article'].lower()}"
            else:
                target = f"aiact/art/{ref['target_article']}"

            target_pin = make_pincite(
                paragraph=ref.get("paragraph"),
                letter=ref.get("letter"),
                subparagraph=ref.get("subparagraph"),
            )
            out.append(emit_reference(
                source=f"aiact/art/{source_article}",
                source_pin=source_pin,
                target=target,
                target_pin=target_pin if target_pin else None,
                kind="cite",
                source_instrument="aiact",
                target_instrument="aiact",
            ))
    return out


def migrate_article_to_recitals(cr: dict) -> list[dict]:
    """article_to_recitals → forward Reference[] (article→recital).
    Article-grain only: no pin-cite info available."""
    out = []
    table = cr.get("article_to_recitals", {}) or {}
    for source_article, recital_numbers in table.items():
        for rec_n in recital_numbers:
            out.append(emit_reference(
                source=f"aiact/art/{source_article}",
                source_pin={},
                target=f"aiact/rec/{rec_n}",
                target_pin=None,
                kind="cite",
                source_instrument="aiact",
                target_instrument="aiact",
            ))
    return out


def migrate_article_to_external_refs(cr: dict) -> list[dict]:
    """article_to_external_refs → forward Reference[] (article→external).
    Target instrument & canonical_id derive from kind + CELEX + target_article."""
    out = []
    table = cr.get("article_to_external_refs", {}) or {}
    for source_article, refs in table.items():
        for ref in refs:
            loc = ref.get("location_in_source") or {}
            source_pin = make_pincite(paragraph=loc.get("paragraph"), letter=loc.get("letter"))

            kind = ref.get("kind", "external_other")
            target_article = ref.get("target_article")
            celex = ref.get("celex")

            if kind == "external_gdpr":
                target_instrument = "gdpr"
                if target_article:
                    target = f"gdpr/art/{target_article}"
                else:
                    target = "gdpr"
            else:
                # external_other: use CELEX as the instrument slug
                if celex:
                    target_instrument = celex
                    if target_article:
                        target = f"{celex}/art/{target_article}"
                    else:
                        target = celex
                else:
                    # No CELEX — preserve the raw text as the target identifier
                    target_instrument = "external"
                    target = ref.get("raw", "")

            target_pin = make_pincite(
                paragraph=ref.get("paragraph"),
                letter=ref.get("letter"),
                subparagraph=ref.get("subparagraph"),
            )
            out.append(emit_reference(
                source=f"aiact/art/{source_article}",
                source_pin=source_pin,
                target=target,
                target_pin=target_pin if target_pin else None,
                kind="cite",
                source_instrument="aiact",
                target_instrument=target_instrument,
            ))
    return out


# ─── Driver ─────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report, but don't write references.json")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not SOURCE_FILE.exists():
        print(f"ERROR: {SOURCE_FILE} not found", file=sys.stderr)
        return 2

    cr = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))

    all_refs: list[dict] = []
    a_to_a = migrate_article_to_articles_internal(cr)
    a_to_r = migrate_article_to_recitals(cr)
    a_to_e = migrate_article_to_external_refs(cr)
    all_refs.extend(a_to_a)
    all_refs.extend(a_to_r)
    all_refs.extend(a_to_e)

    # Sort by source canonical_id, then by target — deterministic output for
    # idempotent diffs.
    all_refs.sort(key=lambda r: (r["source"], r["target"], r.get("sourcePin", {}).get("paragraph", ""),
                                 r.get("sourcePin", {}).get("letter", "")))

    mode_label = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"Phase 2 unified-references migration — {mode_label}")
    print()
    print(f"  source:  {SOURCE_FILE.relative_to(REPO_ROOT)}")
    print(f"  target:  {DEST_FILE.relative_to(REPO_ROOT)}")
    print()
    print(f"  {'segment':40} {'count':>7}")
    print(f"  {'-'*40} {'-'*7}")
    print(f"  {'article→article|annex (4.9 internal)':40} {len(a_to_a):>7}")
    print(f"  {'article→recital':40} {len(a_to_r):>7}")
    print(f"  {'article→external (gdpr/CELEX)':40} {len(a_to_e):>7}")
    print(f"  {'-'*40} {'-'*7}")
    print(f"  {'TOTAL':40} {len(all_refs):>7}")
    print()

    # Sanity: distinct target instruments
    target_instruments = sorted(set(r["targetInstrument"] for r in all_refs))
    print(f"  distinct target instruments ({len(target_instruments)}): {target_instruments[:8]}{'...' if len(target_instruments) > 8 else ''}")
    print()

    # Sanity: edges with non-empty target pin-cite
    with_target_pin = sum(1 for r in all_refs if r.get("targetPin"))
    with_source_pin = sum(1 for r in all_refs if r.get("sourcePin"))
    print(f"  edges with target pin-cite: {with_target_pin}")
    print(f"  edges with source pin-cite: {with_source_pin}")

    if not args.dry_run:
        DEST_FILE.write_text(
            json.dumps(all_refs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print()
        print(f"  wrote {len(json.dumps(all_refs, ensure_ascii=False, indent=2))} bytes to {DEST_FILE.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
