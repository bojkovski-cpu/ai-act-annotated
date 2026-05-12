#!/usr/bin/env python3
"""
verify_canonical_ids.py — Phase 1 canonical-id format validator.

Walks src/data/{articles,recitals,annexes}_{en,nl}.json and asserts:

  (1) Every Article record has canonical_id = 'aiact/art/{number}' and
      version_id = '2024-08-01' (the Phase 1 initial backfill).
  (2) Every Recital record has canonical_id = 'aiact/rec/{number}'.
  (3) Every Annex record has canonical_id = 'aiact/annex/{id.lower()}'.
  (4) For Pattern A annexes (III, IV, V, VI, VII, IX, X, XII, XIII per
      annex-point-grain-aiact-2026-05-12.md), every AnnexPoint has
      canonical_id = 'aiact/annex/{roman}/{position}'.
  (5) For Pattern A annexes with letter sub-points (III, IV, VII, X, XII),
      every AnnexLetter has canonical_id = 'aiact/annex/{roman}/{position}/{letter}'.
  (6) Pattern B (I, VIII, XI) and Pattern C (II) annexes have points = [].
  (7) EN and NL versions of each record agree on canonical_id + version_id
      (these fields are language-agnostic).

Exit codes:
  0  every assertion holds.
  1  at least one record violates an assertion.
  2  a required data file is missing or malformed.

Usage:
    python scripts/verify_canonical_ids.py
    python scripts/verify_canonical_ids.py --verbose

Read-only with respect to the data layer. Designed to run in CI before
every Phase 1 cutover; gated by FF_CANONICAL_IDS once the flag flips.

References:
    control-room/reference/url-contract-aiact-2026-05-12.md
    control-room/reference/annex-point-grain-aiact-2026-05-12.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "src" / "data"

VERSION_ID_INITIAL = "2024-08-01"

PATTERN_A_NUMBERED = frozenset({"III", "IV", "V", "VI", "VII", "IX", "X", "XII"})
PATTERN_A_LETTERED = frozenset({"XIII"})
PATTERN_B = frozenset({"I", "VIII", "XI"})
PATTERN_C = frozenset({"II"})
PATTERN_A = PATTERN_A_NUMBERED | PATTERN_A_LETTERED
WITH_LETTER_SUBPOINTS = frozenset({"III", "IV", "VII", "X", "XII"})


def load(name: str):
    fp = DATA_DIR / name
    if not fp.exists():
        print(f"FAIL: missing data file {fp}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: {name} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)


def expect(condition: bool, msg: str, errors: list[str]) -> None:
    if not condition:
        errors.append(msg)


def check_articles(lang: str, errors: list[str]) -> int:
    data = load(f"articles_{lang}.json")
    if not isinstance(data, list):
        errors.append(f"articles_{lang}.json: top level must be a list")
        return 0
    for record in data:
        num = record.get("number")
        cid = record.get("canonical_id")
        vid = record.get("version_id")
        expected_cid = f"aiact/art/{num}"
        expect(cid == expected_cid,
               f"articles_{lang}.json art={num}: canonical_id={cid!r} (expected {expected_cid!r})", errors)
        expect(vid == VERSION_ID_INITIAL,
               f"articles_{lang}.json art={num}: version_id={vid!r} (expected {VERSION_ID_INITIAL!r})", errors)
    return len(data)


def check_recitals(lang: str, errors: list[str]) -> int:
    data = load(f"recitals_{lang}.json")
    if not isinstance(data, list):
        errors.append(f"recitals_{lang}.json: top level must be a list")
        return 0
    for record in data:
        num = record.get("number")
        cid = record.get("canonical_id")
        vid = record.get("version_id")
        expected_cid = f"aiact/rec/{num}"
        expect(cid == expected_cid,
               f"recitals_{lang}.json rec={num}: canonical_id={cid!r} (expected {expected_cid!r})", errors)
        expect(vid == VERSION_ID_INITIAL,
               f"recitals_{lang}.json rec={num}: version_id={vid!r} (expected {VERSION_ID_INITIAL!r})", errors)
    return len(data)


def check_annexes(lang: str, errors: list[str]) -> tuple[int, int, int]:
    data = load(f"annexes_{lang}.json")
    if not isinstance(data, list):
        errors.append(f"annexes_{lang}.json: top level must be a list")
        return (0, 0, 0)
    n_points, n_letters = 0, 0
    for record in data:
        roman = record.get("id", "")
        cid = record.get("canonical_id")
        vid = record.get("version_id")
        expected_cid = f"aiact/annex/{roman.lower()}"
        expect(cid == expected_cid,
               f"annexes_{lang}.json {roman}: canonical_id={cid!r} (expected {expected_cid!r})", errors)
        expect(vid == VERSION_ID_INITIAL,
               f"annexes_{lang}.json {roman}: version_id={vid!r} (expected {VERSION_ID_INITIAL!r})", errors)

        points = record.get("points")
        expect(isinstance(points, list),
               f"annexes_{lang}.json {roman}: points must be a list", errors)
        if not isinstance(points, list):
            continue

        # Pattern A annexes must have non-empty points;
        # Pattern B + C must have points=[].
        if roman in PATTERN_A:
            expect(len(points) > 0,
                   f"annexes_{lang}.json {roman}: Pattern A but points is empty", errors)
        elif roman in PATTERN_B or roman in PATTERN_C:
            expect(len(points) == 0,
                   f"annexes_{lang}.json {roman}: Pattern B/C must have points=[] (got {len(points)})", errors)
        else:
            errors.append(f"annexes_{lang}.json {roman}: unknown pattern classification")

        # Validate each point and its letters
        for point in points:
            n_points += 1
            position = point.get("position", "")
            p_cid = point.get("canonical_id")
            expected_p_cid = f"aiact/annex/{roman.lower()}/{position}"
            expect(p_cid == expected_p_cid,
                   f"annexes_{lang}.json {roman} point {position}: canonical_id={p_cid!r} (expected {expected_p_cid!r})", errors)

            letters = point.get("letters", [])
            expect(isinstance(letters, list),
                   f"annexes_{lang}.json {roman} point {position}: letters must be a list", errors)
            if not isinstance(letters, list):
                continue

            # Letters only exist for annexes in WITH_LETTER_SUBPOINTS, but
            # NOT every point in those annexes has letters -- check that
            # letters appear only where allowed, but don't force them.
            if letters and roman not in WITH_LETTER_SUBPOINTS:
                errors.append(
                    f"annexes_{lang}.json {roman} point {position}: has letters but annex not in WITH_LETTER_SUBPOINTS"
                )

            for letter in letters:
                n_letters += 1
                ltr = letter.get("letter", "")
                l_cid = letter.get("canonical_id")
                expected_l_cid = f"aiact/annex/{roman.lower()}/{position}/{ltr}"
                expect(l_cid == expected_l_cid,
                       f"annexes_{lang}.json {roman} point {position} letter {ltr}: canonical_id={l_cid!r} (expected {expected_l_cid!r})", errors)
    return (len(data), n_points, n_letters)


def check_bilingual_agreement(errors: list[str]) -> None:
    """canonical_id and version_id are language-agnostic — EN and NL must agree."""
    for (kind, key) in [("articles", "number"), ("recitals", "number"), ("annexes", "id")]:
        en = load(f"{kind}_en.json")
        nl = load(f"{kind}_nl.json")
        en_by_key = {r[key]: r for r in en}
        nl_by_key = {r[key]: r for r in nl}
        for k, en_rec in en_by_key.items():
            nl_rec = nl_by_key.get(k)
            if nl_rec is None:
                continue  # bilingual gap; not this verifier's concern
            for fld in ("canonical_id", "version_id"):
                if en_rec.get(fld) != nl_rec.get(fld):
                    errors.append(
                        f"{kind}: {key}={k}: {fld} disagrees between EN ({en_rec.get(fld)!r}) and NL ({nl_rec.get(fld)!r})"
                    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    errors: list[str] = []
    counts = {}

    for lang in ("en", "nl"):
        counts[f"articles_{lang}"] = check_articles(lang, errors)
        counts[f"recitals_{lang}"] = check_recitals(lang, errors)
        ann, pts, lts = check_annexes(lang, errors)
        counts[f"annexes_{lang}"] = ann
        counts[f"annex_points_{lang}"] = pts
        counts[f"annex_letters_{lang}"] = lts

    check_bilingual_agreement(errors)

    print("verify_canonical_ids.py — Phase 1 canonical-id format validator")
    print()
    print(f"  {'collection':28} {'count':>8}")
    print(f"  {'-'*28} {'-'*8}")
    for k, v in counts.items():
        print(f"  {k:28} {v:>8}")
    print()

    if errors:
        print(f"FAIL ({len(errors)} error(s)):", file=sys.stderr)
        # Print up to 50 errors; cap output to stay readable in CI.
        for err in errors[:50]:
            print(f"  - {err}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more.", file=sys.stderr)
        return 1
    print("PASS — all canonical_id and version_id fields match the Phase 1 contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
