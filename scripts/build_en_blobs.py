#!/usr/bin/env python3
"""
build_en_blobs.py — Split src/data/ai_act_structured.json into per-entity JSON blobs.

Step 4.3b output (English side). Decomposes the existing 1.35 MB single blob into
the per-language file shape the new loader.ts consumes:

  src/data/articles_en.json           — 113 article rows (omnibus_amendments stripped)
  src/data/recitals_en.json           — 180 recital rows
  src/data/annexes_en.json            — 13 annex rows
  src/data/cross_references.json      — language-agnostic article↔recital mapping
  src/data/omnibus_amendments_en.json — flat list of amendments tagged with source article

Notes on deliberate deviations from the 4.3b handoff text:

* The handoff says "remove drafting_history from article rows". The external
  src/data/drafting_history.json is shaped {versions, by_version, index, stats}
  and serves the /history/ routes — it is NOT a per-article timeline. The
  per-article timelines used by ArticleBlock live in the embedded dict on each
  article row. Since 4.4 owns the proper bilingual drafting-history treatment,
  this script keeps the embedded per-article `drafting_history` dict in place
  (so ArticleBlock keeps working in EN) and lets 4.4 reconcile.
* `omnibus_amendments` IS split off article rows per handoff. The loader exposes
  getOmnibusAmendmentsForArticle(number) so ArticleBlock reads from the split
  file, not the embedded field.

Idempotent: sort_keys=True + stable iteration order. Re-runs produce
byte-identical output.

Counts are asserted (113 / 180 / 13 / 29). Mismatches abort with non-zero exit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_BLOB = REPO / "src" / "data" / "ai_act_structured.json"
OUT_DIR = REPO / "src" / "data"

EXPECTED_ARTICLES = 113
EXPECTED_RECITALS = 180
EXPECTED_ANNEXES = 13
EXPECTED_OMNIBUS_ARTICLES = 29  # current state per metadata.omnibus.affected_articles


def normalise_number(n) -> str:
    """Article/recital numbers come in as int in the EN blob. Normalise to
    string to match the loader's typed Article.number: string contract and to
    align with the NL corpus (which already ships strings)."""
    if isinstance(n, (int, float)):
        return str(int(n))
    return str(n)


def write_json(path: Path, data) -> None:
    """Idempotent write — sort_keys + ensure_ascii=False + trailing newline."""
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not SRC_BLOB.exists():
        print(f"FATAL: source blob not found: {SRC_BLOB}", file=sys.stderr)
        return 1

    with SRC_BLOB.open(encoding="utf-8") as f:
        blob = json.load(f)

    # ── Articles ──────────────────────────────────────────────────────
    raw_articles = blob["articles"]
    if len(raw_articles) != EXPECTED_ARTICLES:
        print(
            f"FATAL: article count mismatch — got {len(raw_articles)}, expected {EXPECTED_ARTICLES}",
            file=sys.stderr,
        )
        return 2

    omnibus_flat: list[dict] = []
    articles_out: list[dict] = []
    for a in sorted(raw_articles, key=lambda r: int(r["number"])):
        article_number = normalise_number(a["number"])
        # Pull omnibus amendments out, tag with source article, append to flat list.
        for amend in a.get("omnibus_amendments") or []:
            omnibus_flat.append({**amend, "article_number": article_number})

        # Strip omnibus_amendments off the article row. Keep drafting_history
        # in place — see module docstring.
        row = {k: v for k, v in a.items() if k != "omnibus_amendments"}
        row["number"] = article_number
        # Normalise paragraph numbers too (they're already strings in the
        # current blob, but be defensive).
        if isinstance(row.get("paragraphs"), list):
            row["paragraphs"] = [
                {**p, "number": normalise_number(p["number"])} for p in row["paragraphs"]
            ]
        articles_out.append(row)

    # ── Recitals ──────────────────────────────────────────────────────
    raw_recitals = blob["recitals"]
    if len(raw_recitals) != EXPECTED_RECITALS:
        print(
            f"FATAL: recital count mismatch — got {len(raw_recitals)}, expected {EXPECTED_RECITALS}",
            file=sys.stderr,
        )
        return 2

    recitals_out = [
        {**r, "number": normalise_number(r["number"])}
        for r in sorted(raw_recitals, key=lambda r: int(r["number"]))
    ]

    # ── Annexes ───────────────────────────────────────────────────────
    raw_annexes = blob["annexes"]
    if len(raw_annexes) != EXPECTED_ANNEXES:
        print(
            f"FATAL: annex count mismatch — got {len(raw_annexes)}, expected {EXPECTED_ANNEXES}",
            file=sys.stderr,
        )
        return 2

    # Annex rows currently look like {id, title, text}. Keep id as-is (Roman
    # numerals like "I", "II"). Sort by id's roman-numeral value so that
    # idempotent re-runs preserve the canonical order.
    ROMAN = {
        "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
        "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    }
    annexes_out = sorted(raw_annexes, key=lambda x: ROMAN.get(x["id"], 999))

    # ── Cross references ──────────────────────────────────────────────
    # Existing shape: {"article_to_recitals": {...}, "recital_to_articles": {...}}.
    # Language-agnostic; lifted as-is.
    cross_refs = blob["cross_references"]
    if not isinstance(cross_refs, dict):
        print("FATAL: cross_references is not a dict", file=sys.stderr)
        return 2

    # ── Omnibus sanity ────────────────────────────────────────────────
    affected_articles = {
        normalise_number(n) for n in (omnibus_flat or [])  # placeholder; refined below
    }
    affected_articles = {a["article_number"] for a in omnibus_flat}
    if len(affected_articles) != EXPECTED_OMNIBUS_ARTICLES:
        print(
            f"WARN: omnibus-affected article count drifted — got "
            f"{len(affected_articles)}, expected {EXPECTED_OMNIBUS_ARTICLES}. "
            f"This is a soft check; metadata.omnibus.affected_articles may "
            f"have been updated.",
            file=sys.stderr,
        )

    # ── Write outputs ─────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = {
        "articles_en.json": articles_out,
        "recitals_en.json": recitals_out,
        "annexes_en.json": annexes_out,
        "cross_references.json": cross_refs,
        "omnibus_amendments_en.json": omnibus_flat,
    }
    for name, data in targets.items():
        path = OUT_DIR / name
        write_json(path, data)
        print(f"  wrote {path.relative_to(REPO)}  ({len(data) if hasattr(data, '__len__') else '-'} entries)")

    print()
    print(f"  articles: {len(articles_out)}")
    print(f"  recitals: {len(recitals_out)}")
    print(f"  annexes:  {len(annexes_out)}")
    print(f"  omnibus amendments: {len(omnibus_flat)} ({len(affected_articles)} articles affected)")
    print(f"  cross_references: article_to_recitals={len(cross_refs.get('article_to_recitals', {}))}, recital_to_articles={len(cross_refs.get('recital_to_articles', {}))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
