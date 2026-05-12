#!/usr/bin/env python3
"""
Phase 1 — canonical_id + version_id backfill for the AI Act Annotated corpus.

Walks src/data/{articles,recitals,annexes}_{en,nl}.json and:
  * adds canonical_id + version_id ('2024-08-01') to every record,
  * for Pattern A annexes (III, IV, V, VI, VII, IX, X, XII, XIII per
    annex-point-grain-aiact-2026-05-12.md), parses the `text` field into
    AnnexPoint records with optional letter sub-points and emits a
    `points: AnnexPoint[]` field on the annex,
  * for Pattern B (I, VIII, XI) and Pattern C (II) annexes, emits an
    empty `points: []` and leaves the text intact.

Idempotent: running twice produces byte-identical output.

Usage:
    python3 scripts/migrate_canonical_ids.py [--dry-run] [--verbose]

References:
    control-room/reference/url-contract-aiact-2026-05-12.md
    control-room/reference/annex-point-grain-aiact-2026-05-12.md
    src/types/aiact.ts (CanonicalId, VersionId, Annex, AnnexPoint, AnnexLetter)
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ─── Configuration ─────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "src" / "data"

# Regulation entry into force per OJ L, 2024/1689, 12.7.2024. All Phase 1
# records get this version_id; Phase 6 introduces forward-dated versions
# for forthcoming Omnibus amendments.
VERSION_ID_INITIAL = "2024-08-01"

# Pattern classification per annex-point-grain-aiact-2026-05-12.md.
PATTERN_A_NUMBERED = frozenset({"III", "IV", "V", "VI", "VII", "IX", "X", "XII"})
PATTERN_A_LETTERED = frozenset({"XIII"})
PATTERN_B = frozenset({"I", "VIII", "XI"})
PATTERN_C = frozenset({"II"})

# Annexes whose numbered points have letter sub-points in the source text.
WITH_LETTER_SUBPOINTS = frozenset({"III", "IV", "VII", "X", "XII"})

# ─── Annex text parser ─────────────────────────────────────────────────

# Strip markdown heading markers (#+ ) and bullet markers (- ) from the
# start of a line. Multiple prefixes can stack: "  - 1. ..." or "### 1. ..."
PREFIX_RE = re.compile(r"^\s*(?:#+\s+|-\s+)*")
NUMBERED_RE = re.compile(r"^(\d+)\.(?:\s+(.+?))?\s*$")
LETTER_RE = re.compile(r"^\(?([a-z])\)(?:\s+(.+?))?\s*$")


def strip_prefix(line: str) -> str:
    return PREFIX_RE.sub("", line).strip()


def split_top_level(text: str, kind: str):
    """Walk `text` and return [(label, body_lines), …] for top-level points.

    `kind` is 'numbered' or 'lettered'.
    Body lines are kept verbatim (no stripping) so paragraph structure
    inside a point is preserved for the renderer.
    """
    marker = NUMBERED_RE if kind == "numbered" else LETTER_RE
    points = []
    label = None
    body = []
    for line in text.split("\n"):
        stripped = strip_prefix(line)
        m = marker.match(stripped) if stripped else None
        if m:
            if label is not None:
                points.append((label, body))
            label = m.group(1)
            body = [m.group(2)] if m.group(2) else []
        elif label is not None:
            body.append(line)
    if label is not None:
        points.append((label, body))
    return points


def split_sub_letters(body_lines):
    """Split a body into (pre_letter_lines, [(letter, lines), …])."""
    out = []
    pre = []
    cur = None
    lines = []
    for line in body_lines:
        stripped = strip_prefix(line)
        m = LETTER_RE.match(stripped) if stripped else None
        if m:
            if cur is not None:
                out.append((cur, lines))
            cur = m.group(1)
            lines = [m.group(2)] if m.group(2) else []
        else:
            (lines if cur is not None else pre).append(line)
    if cur is not None:
        out.append((cur, lines))
    return pre, out


def normalise_body(lines):
    """Join lines with newlines, strip trailing whitespace per line,
    and trim leading/trailing blank lines from the joined block."""
    return "\n".join(l.rstrip() for l in lines).strip()


# ─── Canonical-ID derivation ───────────────────────────────────────────


def cid_article(num: str) -> str:
    return f"aiact/art/{num}"


def cid_recital(num: str) -> str:
    return f"aiact/rec/{num}"


def cid_annex(roman: str) -> str:
    return f"aiact/annex/{roman.lower()}"


def cid_annex_point(roman: str, position: str) -> str:
    return f"aiact/annex/{roman.lower()}/{position}"


def cid_annex_letter(roman: str, position: str, letter: str) -> str:
    return f"aiact/annex/{roman.lower()}/{position}/{letter}"


# ─── Per-collection migrators ──────────────────────────────────────────


ARTICLE_KEY_ORDER = [
    "canonical_id", "version_id", "number", "label", "title",
    "paragraphs", "chapter", "chapter_roman", "chapter_title",
    "related_recitals", "drafting_history",
]

RECITAL_KEY_ORDER = ["canonical_id", "version_id", "number", "text"]

ANNEX_KEY_ORDER = [
    "canonical_id", "version_id", "id", "title", "text", "points",
]


def reorder(record: dict, order: list) -> dict:
    """Return a new dict with keys in `order` first, remaining keys after.
    Unknown keys are preserved in their original relative order."""
    new = {}
    for k in order:
        if k in record:
            new[k] = record[k]
    for k, v in record.items():
        if k not in new:
            new[k] = v
    return new


def migrate_articles(filepath: Path):
    data = json.loads(filepath.read_text(encoding="utf-8"))
    for record in data:
        record["canonical_id"] = cid_article(record["number"])
        record["version_id"] = VERSION_ID_INITIAL
    data = [reorder(r, ARTICLE_KEY_ORDER) for r in data]
    return data, {"records": len(data)}


def migrate_recitals(filepath: Path):
    data = json.loads(filepath.read_text(encoding="utf-8"))
    for record in data:
        record["canonical_id"] = cid_recital(record["number"])
        record["version_id"] = VERSION_ID_INITIAL
    data = [reorder(r, RECITAL_KEY_ORDER) for r in data]
    return data, {"records": len(data)}


def build_annex_points(roman: str, text: str):
    """Parse a Pattern A annex's text into structured points."""
    if roman in PATTERN_A_LETTERED:
        raw = split_top_level(text, "lettered")
    elif roman in PATTERN_A_NUMBERED:
        raw = split_top_level(text, "numbered")
    else:
        return []

    has_subs = roman in WITH_LETTER_SUBPOINTS
    points = []
    for position, body_lines in raw:
        if has_subs:
            pre, letters_raw = split_sub_letters(body_lines)
            body_text = normalise_body(pre)
            letters = [
                {
                    "canonical_id": cid_annex_letter(roman, position, letter),
                    "letter": letter,
                    "text": normalise_body(lines),
                }
                for letter, lines in letters_raw
            ]
        else:
            body_text = normalise_body(body_lines)
            letters = []
        points.append({
            "canonical_id": cid_annex_point(roman, position),
            "position": position,
            "body": body_text,
            "letters": letters,
        })
    return points


def migrate_annexes(filepath: Path):
    data = json.loads(filepath.read_text(encoding="utf-8"))
    n_points, n_letters = 0, 0
    for record in data:
        roman = record["id"]
        record["canonical_id"] = cid_annex(roman)
        record["version_id"] = VERSION_ID_INITIAL
        if roman in PATTERN_A_NUMBERED or roman in PATTERN_A_LETTERED:
            pts = build_annex_points(roman, record["text"])
            record["points"] = pts
            n_points += len(pts)
            n_letters += sum(len(p["letters"]) for p in pts)
        else:
            record["points"] = []
    data = [reorder(r, ANNEX_KEY_ORDER) for r in data]
    return data, {"records": len(data), "points": n_points, "letters": n_letters}


# ─── Driver ────────────────────────────────────────────────────────────


def write_json(data, filepath: Path, dry_run: bool) -> int:
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if not dry_run:
        filepath.write_text(out, encoding="utf-8")
    return len(out.encode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="parse + format but don't write the JSON files")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    plan = [
        ("articles_en.json", migrate_articles),
        ("articles_nl.json", migrate_articles),
        ("recitals_en.json", migrate_recitals),
        ("recitals_nl.json", migrate_recitals),
        ("annexes_en.json",  migrate_annexes),
        ("annexes_nl.json",  migrate_annexes),
    ]

    mode_label = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"Phase 1 canonical-id migration — {mode_label}")
    print(f"  data dir:   {DATA_DIR}")
    print(f"  version_id: {VERSION_ID_INITIAL}")
    print()
    print(f"  {'file':28} | {'records':>7} | {'extras':30} | {'bytes':>8}")
    print(f"  {'-'*28}-+-{'-'*7}-+-{'-'*30}-+-{'-'*8}")

    for filename, fn in plan:
        fp = DATA_DIR / filename
        if not fp.exists():
            print(f"  {filename:28} | MISSING — skipped")
            continue
        data, stats = fn(fp)
        size = write_json(data, fp, args.dry_run)
        extras = ""
        if "points" in stats:
            extras = f"{stats['points']} points, {stats['letters']} letters"
        print(f"  {filename:28} | {stats['records']:>7} | {extras:30} | {size:>8}")

    print()
    print(f"Phase 1 — {mode_label}.  Flag still false in flags.json;")
    print("flip FF_CANONICAL_IDS in a separate one-line PR after this migration commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
