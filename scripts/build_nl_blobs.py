#!/usr/bin/env python3
"""
build_nl_blobs.py — Concatenate dutch-intermediate per-file JSONs into per-language blobs.

Step 4.3b output (Dutch side). Reads:

  dutch-intermediate/regulation/articles/chapter-NN/article-NN.json   (113 files)
  dutch-intermediate/regulation/recitals/recital-NNN.json             (180 files)
  dutch-intermediate/regulation/annexes/annex-{i,ii,...}.json         (13 files)

Writes:

  src/data/articles_nl.json   (113 article rows, parallel shape to articles_en.json)
  src/data/recitals_nl.json   (180 recital rows)
  src/data/annexes_nl.json    (13 annex rows)

Schema notes:

* The NL corpus ships a single body_md blob per article. The EN corpus ships a
  structured paragraphs[{id, number, text}] array. ArticleBlock.astro iterates
  paragraphs[]. To keep the component working unmodified across both languages,
  this script parses NL body_md into the EN paragraph shape:

    - **N.** at line start  → paragraph N
    - "- a) text"           → "(a)\ntext"   (EN's line-broken sub-point format)
    - "- 1) text"           → "(1)\ntext"   (numbered sub-points, e.g. Article 3 definitions)
    - paragraph text prefixed with "N.   " (three spaces) to mirror EN exactly

* Articles with no paragraph markers (e.g. Article 3 Definitions, Article 4 AI
  literacy) collapse to a single paragraph row with id=null, number=null —
  matching EN's behaviour for the same articles.

* `related_recitals`, `omnibus_amendments`, `drafting_history`, and
  `cross_references` are language-agnostic and intentionally NOT carried on
  NL article rows. The loader stitches them in at read time from the EN-side
  files (cross_references.json, omnibus_amendments_en.json) — Decision 5
  hybrid model.

* Chapters list: derived from the chapter_title field on each article row.
  Chapter numbers and roman numerals are language-agnostic; titles vary.

Idempotency: sort_keys=True, stable iteration order. Re-runs produce
byte-identical output.

Counts: 113 / 180 / 13 — asserted, fail-loud on mismatch.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NL_REG = REPO / "dutch-intermediate" / "regulation"
OUT_DIR = REPO / "src" / "data"

EXPECTED_ARTICLES = 113
EXPECTED_RECITALS = 180
EXPECTED_ANNEXES = 13

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
}


# ── body_md → paragraphs[] parser ────────────────────────────────────

BOLD_PARA_RE = re.compile(r"^\*\*(\d+)\.\*\*\s*", re.M)
SUBPOINT_RE = re.compile(r"^-\s+([a-z0-9ivxIVX]+)\)\s*", re.M)


def _clean_inline_markers(text: str) -> str:
    """Convert "- a) Foo bar" to "(a)\nFoo bar" — EN's line-broken sub-point
    format, which ArticleBlock's parseSubPoints regex (^\([a-z]\)) consumes.
    Also normalise sub-point markers that use digits or roman numerals."""
    return SUBPOINT_RE.sub(lambda m: f"({m.group(1)})\n", text)


def parse_body_md(body_md: str, article_number: str) -> list[dict]:
    """Parse NL article body_md into the EN paragraph shape.

    Output: list of {id, number, text} dicts. id format mirrors EN:
    `<3-digit-article>.<3-digit-paragraph>` (e.g. "001.002"). For articles
    without paragraph markers, returns a single row with id=None, number=None
    and the full body as text — matching EN's behaviour for those articles.
    """
    matches = list(BOLD_PARA_RE.finditer(body_md))

    if not matches:
        # No paragraph markers — collapse to a single unnumbered paragraph,
        # matching EN's shape for articles like Article 3 (definitions).
        text = _clean_inline_markers(body_md.strip())
        return [{"id": None, "number": None, "text": text}]

    paragraphs = []
    art_int = int(article_number)
    for i, m in enumerate(matches):
        num = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body_md)
        para_body = body_md[start:end].strip()
        para_body = _clean_inline_markers(para_body)
        # EN visual style: "N.   <body>" with three spaces after the dot.
        text = f"{num}.   {para_body}"
        paragraphs.append(
            {
                "id": f"{art_int:03d}.{int(num):03d}",
                "number": num,
                "text": text,
            }
        )
    return paragraphs


# ── Article processing ───────────────────────────────────────────────

def build_article_row(src: dict) -> dict:
    """Convert a dutch-intermediate article JSON to articles_nl.json shape.

    Output keys mirror articles_en.json (subset — see module docstring):
      number, label, title, paragraphs, chapter, chapter_roman, chapter_title

    Notes:
      - chapter is normalised to int (matches EN); chapter_number_roman → chapter_roman
      - article_title → title; article_number → number (string)
      - label is constructed: "Artikel N"
    """
    article_number = str(src["article_number"]).strip()
    chapter_str = str(src["chapter_number"]).strip()
    return {
        "number": article_number,
        "label": f"Artikel {article_number}",
        "title": src["article_title"],
        "paragraphs": parse_body_md(src["body_md"], article_number),
        "chapter": int(chapter_str) if chapter_str.isdigit() else chapter_str,
        "chapter_roman": src["chapter_number_roman"],
        "chapter_title": src["chapter_title"],
    }


def build_recital_row(src: dict) -> dict:
    """Convert a dutch-intermediate recital JSON to recitals_nl.json shape.

    EN recital rows are minimal: {number, text}. NL ships body_md plus
    metadata (source_url, scraped_at, etc.) — strip to the EN shape.
    """
    return {
        "number": str(src["recital_number"]).strip(),
        # body_md is wrapped to ~78 cols on the source side — but EN's `text`
        # is single-paragraph prose. Strip the trailing newline.
        "text": src["body_md"].strip(),
    }


def build_annex_row(src: dict) -> dict:
    """Convert a dutch-intermediate annex JSON to annexes_nl.json shape.

    EN annex rows: {id, title, text}. NL ships body_md (markdown) — pass
    through as `text`, with id derived from the roman numeral.
    """
    return {
        "id": src["annex_number_roman"],
        "title": src["annex_title"],
        "text": src["body_md"].strip(),
    }


# ── I/O ──────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not NL_REG.exists():
        print(f"FATAL: NL source directory not found: {NL_REG}", file=sys.stderr)
        return 1

    # ── Articles ──────────────────────────────────────────────────────
    article_paths = sorted(NL_REG.glob("articles/chapter-*/article-*.json"))
    if len(article_paths) != EXPECTED_ARTICLES:
        print(
            f"FATAL: NL article file count mismatch — got {len(article_paths)}, "
            f"expected {EXPECTED_ARTICLES}",
            file=sys.stderr,
        )
        return 2

    articles_out = []
    for p in article_paths:
        src = load_json(p)
        articles_out.append(build_article_row(src))
    # Stable order: by integer article number.
    articles_out.sort(key=lambda r: int(r["number"]))

    # Cross-check counts: should still be 113 after parsing.
    if len(articles_out) != EXPECTED_ARTICLES:
        print(f"FATAL: post-parse article count drift", file=sys.stderr)
        return 2

    # ── Recitals ──────────────────────────────────────────────────────
    recital_paths = sorted(NL_REG.glob("recitals/recital-*.json"))
    if len(recital_paths) != EXPECTED_RECITALS:
        print(
            f"FATAL: NL recital file count mismatch — got {len(recital_paths)}, "
            f"expected {EXPECTED_RECITALS}",
            file=sys.stderr,
        )
        return 2

    recitals_out = []
    for p in recital_paths:
        src = load_json(p)
        recitals_out.append(build_recital_row(src))
    recitals_out.sort(key=lambda r: int(r["number"]))

    # ── Annexes ───────────────────────────────────────────────────────
    annex_paths = sorted(NL_REG.glob("annexes/annex-*.json"))
    if len(annex_paths) != EXPECTED_ANNEXES:
        print(
            f"FATAL: NL annex file count mismatch — got {len(annex_paths)}, "
            f"expected {EXPECTED_ANNEXES}",
            file=sys.stderr,
        )
        return 2

    annexes_out = []
    for p in annex_paths:
        src = load_json(p)
        annexes_out.append(build_annex_row(src))
    annexes_out.sort(key=lambda r: ROMAN_TO_INT.get(r["id"], 999))

    # ── Write ─────────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = {
        "articles_nl.json": articles_out,
        "recitals_nl.json": recitals_out,
        "annexes_nl.json": annexes_out,
    }
    for name, data in targets.items():
        path = OUT_DIR / name
        write_json(path, data)
        print(f"  wrote {path.relative_to(REPO)}  ({len(data)} entries)")

    print()
    print(f"  articles: {len(articles_out)}")
    print(f"  recitals: {len(recitals_out)}")
    print(f"  annexes:  {len(annexes_out)}")

    # Soft sanity check: spot-check a paragraph from article 1.
    a1 = next(a for a in articles_out if a["number"] == "1")
    print(
        f"  spot-check art.1 paragraphs: {len(a1['paragraphs'])} "
        f"(first text starts: {a1['paragraphs'][0]['text'][:60]!r})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
