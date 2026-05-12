#!/usr/bin/env python3
"""
Phase 4 — AmendmentInstrument + AmendmentCallout migration.

Reads src/data/omnibus_amendments_en.json (29 records: action/article_number/
paragraph/sub_provision/summary) and emits:

  * src/data/amendment_instruments.json — 1 record describing the
    COM(2025) 836 AI Omnibus package as a whole.

  * src/data/amendment_callouts.json — 29 records, one per affected
    paragraph, each pointing back at the instrument via
    amendingInstrument.canonicalId.

Action → redline.kind mapping:
  replaced  → replace
  inserted  → insert
  added     → insert  (added = inserted from nothing)
  deleted   → delete
  amended   → replace (catch-all in-place change)

Notes:
  * `summary` from the source becomes `redline.summary` (LocalizedText)
    on the callout. oldText/newText left undefined — the original parser
    didn't capture the actual amended text; content ops fills later.
  * `sub_provision` is preserved verbatim as affectedSubparagraphId
    (free-form string; the parser produced things like "1(2), point (g)"
    or "3 — new points (14a) and (14b)").
  * status = 'proposed' uniformly; COM(2025) 836 is the proposal, not yet
    adopted by Council + Parliament.
  * effectiveDate left undefined — no real entry-into-force date yet.

Idempotent.

Usage:
    python3 scripts/migrate_amendment_instruments.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "src" / "data"

SOURCE_FILE = DATA_DIR / "omnibus_amendments_en.json"
DEST_INSTRUMENTS = DATA_DIR / "amendment_instruments.json"
DEST_CALLOUTS = DATA_DIR / "amendment_callouts.json"

INSTRUMENT_CANONICAL = "aiact-omnibus-2025"
INSTRUMENT_SHORT_TITLE = {
    "en": "AI Omnibus Package (COM(2025) 836)",
    "nl": "AI Omnibus-pakket (COM(2025) 836)",
}
INSTRUMENT_LONG_TITLE_EN = (
    "Proposal for a Regulation of the European Parliament and of the Council "
    "amending Regulation (EU) 2024/1689 (the AI Act) and other Union acts"
)
INSTRUMENT_SOURCE_LABEL = "COM(2025) 836 final"

ACTION_TO_REDLINE_KIND = {
    "replaced": "replace",
    "inserted": "insert",
    "added":    "insert",
    "deleted":  "delete",
    "amended":  "replace",
}


def callout_id(record: dict) -> str:
    """Stable hash from the source record fields."""
    blob = json.dumps({
        "art": record.get("article_number"),
        "par": record.get("paragraph"),
        "sub": record.get("sub_provision"),
        "act": record.get("action"),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SOURCE_FILE.exists():
        print(f"ERROR: {SOURCE_FILE} not found", file=sys.stderr)
        return 2

    src = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    if not isinstance(src, list):
        print(f"ERROR: {SOURCE_FILE} must be a list", file=sys.stderr)
        return 2

    # Build the AmendmentInstrument record (single, for the omnibus).
    affected = sorted({f"aiact/art/{r['article_number']}" for r in src},
                      key=lambda s: int(s.split('/')[-1]) if s.split('/')[-1].isdigit() else 999)
    instrument = {
        "canonicalId": INSTRUMENT_CANONICAL,
        "kind": "omnibus",
        "shortTitle": INSTRUMENT_SHORT_TITLE,
        "longTitle": {"en": INSTRUMENT_LONG_TITLE_EN},
        "sourceLabel": INSTRUMENT_SOURCE_LABEL,
        "status": "proposed",
        "affects": affected,
    }

    # Build the AmendmentCallout records (one per source row).
    callouts = []
    for r in src:
        kind = ACTION_TO_REDLINE_KIND.get(r["action"])
        if kind is None:
            print(f"WARN: unknown action {r['action']!r} on article {r['article_number']}", file=sys.stderr)
            continue
        callout = {
            "id": callout_id(r),
            "affectedArticle": f"aiact/art/{r['article_number']}",
            "affectedParagraphId": str(r["paragraph"]),
            "status": "proposed",
            "redline": {
                "kind": kind,
                "summary": {"en": r["summary"]},
            },
            "amendingInstrument": {
                "canonicalId": INSTRUMENT_CANONICAL,
                "shortTitle": INSTRUMENT_SHORT_TITLE,
            },
        }
        if r.get("sub_provision"):
            callout["affectedSubparagraphId"] = r["sub_provision"]
        callouts.append(callout)

    # Sort callouts by affected article number for deterministic output.
    callouts.sort(key=lambda c: (
        int(c["affectedArticle"].split("/")[-1]) if c["affectedArticle"].split("/")[-1].isdigit() else 999,
        c["affectedParagraphId"],
        c["affectedSubparagraphId"] if "affectedSubparagraphId" in c else "",
    ))

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"Phase 4 amendment-instruments migration — {mode}")
    print()
    print(f"  source:        {SOURCE_FILE.relative_to(REPO_ROOT)} ({len(src)} records)")
    print(f"  → instruments: {DEST_INSTRUMENTS.relative_to(REPO_ROOT)} (1 record)")
    print(f"  → callouts:    {DEST_CALLOUTS.relative_to(REPO_ROOT)} ({len(callouts)} records)")
    print()
    print(f"  omnibus instrument: canonicalId={INSTRUMENT_CANONICAL!r}")
    print(f"                      status='proposed'")
    print(f"                      affects {len(affected)} articles")
    print()
    print(f"  callouts by redline kind:")
    by_kind = {}
    for c in callouts:
        k = c["redline"]["kind"]
        by_kind[k] = by_kind.get(k, 0) + 1
    for k, n in sorted(by_kind.items()):
        print(f"    {k:8}  {n}")

    if not args.dry_run:
        DEST_INSTRUMENTS.write_text(
            json.dumps([instrument], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        DEST_CALLOUTS.write_text(
            json.dumps(callouts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print()
        print(f"  wrote {DEST_INSTRUMENTS.stat().st_size} bytes to amendment_instruments.json")
        print(f"  wrote {DEST_CALLOUTS.stat().st_size} bytes to amendment_callouts.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
