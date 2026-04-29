#!/usr/bin/env python3
"""
extract_article_references.py — Step 4.9a parser.

Reads src/data/articles_en.json. For every article body, extracts inline
article-reference patterns (Article N, Articles N to M, "Article 6 of
Regulation (EU) 2016/679", etc.) and classifies each into one of three
kinds:

    internal       — refers to another article (or annex) of THIS regulation
    external_gdpr  — refers to Regulation (EU) 2016/679 (the GDPR)
    external_other — refers to any other named EU instrument

Writes three new top-level keys into src/data/cross_references.json,
preserving the existing `article_to_recitals` and `recital_to_articles`:

    article_to_articles_internal   per-source article  -> list[InternalReference]
    article_to_external_refs       per-source article  -> list[ExternalReference]
    articles_referencing           per-target article  -> list[InternalReverseReference]

Idempotent: deterministic key ordering + sort_keys + UTF-8 + trailing newline.

Coverage report is written to control-room/reference/article-references-
coverage-YYYY-MM-DD.md (tracked by Pavle's house-principle docs as the
canonical place for parser introspection).

Notes on scope (Phase v1.1, AI Act):
- We parse ONLY the EN corpus. Article numbers are language-agnostic; the
  loader resolves to NL surface form at render time.
- We skip Article 3 "Definitions" carefully — it contains lots of inline
  citations to OTHER instruments but its sub_points carry numeric labels
  like "(1)", "(2)" rather than "(a)" so location_in_source.letter is None.
- Pin-cite anchor scrolling is out of scope for this step (4.9b decides).
- text_offset is NOT recorded — the renderer re-runs a lightweight regex
  per article. See handoff "Known gotchas" — fragility of offsets vs the
  benefit of recomputability is the trade-off Pavle accepted.

Usage:
    python scripts/extract_article_references.py
    python scripts/extract_article_references.py --report-only  # don't write JSON

Exit codes:
    0 — success (counts written, report generated)
    1 — input missing
    2 — write/encoding error
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ─── Paths ─────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parent.parent
SRC_ARTICLES = REPO / "src" / "data" / "articles_en.json"
SRC_CROSS_REFS = REPO / "src" / "data" / "cross_references.json"
CTRL_ROOM_REF = REPO.parent / "control-room" / "reference"

# ─── Alias table ───────────────────────────────────────────────────────

# Maps short-name surface forms to CELEX. Extensible; additions discovered
# during extraction are documented in the coverage report.
SHORT_NAME_TO_CELEX: dict[str, tuple[str, str]] = {
    # short_name (case-insensitive lookup) -> (celex, official_short_name)
    "GDPR": ("32016R0679", "GDPR"),
    "General Data Protection Regulation": ("32016R0679", "GDPR"),
    "LED": ("32016L0680", "LED"),
    "Law Enforcement Directive": ("32016L0680", "LED"),
    "ePrivacy Directive": ("32002L0058", "ePrivacy Directive"),
    "ePrivacy": ("32002L0058", "ePrivacy Directive"),
    "NIS2 Directive": ("32022L2555", "NIS2 Directive"),
    "NIS2": ("32022L2555", "NIS2 Directive"),
    "DSA": ("32022R2065", "DSA"),
    "Digital Services Act": ("32022R2065", "DSA"),
    "DMA": ("32022R1925", "DMA"),
    "Digital Markets Act": ("32022R1925", "DMA"),
    "DORA": ("32022R2554", "DORA"),
    "Open Data Directive": ("32019L1024", "Open Data Directive"),
}

GDPR_CELEX = "32016R0679"

# The AI Act's OWN CELEX. Any "Regulation (EU) 2024/1689" mention is a
# self-reference, NOT an external citation. Articles 102–110 are amendments
# to other regulations that bake the AI Act's official short title into the
# amended text — so they parse as "external" with this CELEX, but
# semantically they're internal pointers back to this regulation.
AI_ACT_CELEX = "32024R1689"

# Sorted longest-first so "General Data Protection Regulation" beats "GDPR"
# in the same position when both could match.
_SHORT_NAME_KEYS_BY_LEN = sorted(SHORT_NAME_TO_CELEX.keys(), key=len, reverse=True)

# ─── Instrument citation patterns ──────────────────────────────────────

# Each entry: (compiled regex, kind label, extractor returning CELEX + official_name)
def _celex_reg(year: str, num: str) -> str:
    return f"3{year}R{int(num):04d}"


def _celex_dir(year: str, num: str) -> str:
    return f"3{year}L{int(num):04d}"


def _celex_dec(year: str, num: str) -> str:
    return f"3{year}D{int(num):04d}"


# Note: order matters. The OLD-style ("No NNN/YYYY") patterns must be tried
# BEFORE the new-style patterns where applicable, because "Regulation (EU)"
# can be followed by either "No 1025/2012" or "2016/679".
INSTRUMENT_PATTERNS: list[tuple[re.Pattern[str], str, callable]] = [
    # Old-style EU regulation: "Regulation (EU) No 1025/2012"
    (
        re.compile(r"Regulation\s*\(EU\)\s*No\.?\s*(?P<num>\d+)\s*/\s*(?P<year>\d{4})"),
        "regulation_eu_old",
        lambda m: (
            _celex_reg(m["year"], m["num"]),
            f"Regulation (EU) No {m['num']}/{m['year']}",
        ),
    ),
    # New-style EU regulation: "Regulation (EU) 2016/679"
    (
        re.compile(r"Regulation\s*\(EU\)\s*(?P<year>\d{4})\s*/\s*(?P<num>\d+)"),
        "regulation_eu_new",
        lambda m: (
            _celex_reg(m["year"], m["num"]),
            f"Regulation (EU) {m['year']}/{m['num']}",
        ),
    ),
    # EC regulation: "Regulation (EC) No 765/2008" or "Regulation (EC) 300/2008"
    (
        re.compile(r"Regulation\s*\(EC\)\s*(?:No\.?\s*)?(?P<num>\d+)\s*/\s*(?P<year>\d{4})"),
        "regulation_ec",
        lambda m: (
            _celex_reg(m["year"], m["num"]),
            f"Regulation (EC) No {m['num']}/{m['year']}",
        ),
    ),
    # New-style EU directive: "Directive (EU) 2016/680"
    (
        re.compile(r"Directive\s*\(EU\)\s*(?P<year>\d{4})\s*/\s*(?P<num>\d+)"),
        "directive_eu_new",
        lambda m: (
            _celex_dir(m["year"], m["num"]),
            f"Directive (EU) {m['year']}/{m['num']}",
        ),
    ),
    # Plain directive: "Directive 2002/58/EC", "Directive 2014/90/EU"
    (
        re.compile(r"Directive\s+(?P<year>\d{4})\s*/\s*(?P<num>\d+)\s*/\s*(?P<suffix>EU|EC)"),
        "directive_plain",
        lambda m: (
            _celex_dir(m["year"], m["num"]),
            f"Directive {m['year']}/{m['num']}/{m['suffix']}",
        ),
    ),
    # Decision: "Decision (EU) 2024/1234"
    (
        re.compile(r"Decision\s*\(EU\)\s*(?P<year>\d{4})\s*/\s*(?P<num>\d+)"),
        "decision_eu_new",
        lambda m: (
            _celex_dec(m["year"], m["num"]),
            f"Decision (EU) {m['year']}/{m['num']}",
        ),
    ),
]

# ─── Article / Annex parsing ───────────────────────────────────────────

ARTICLE_KEYWORD_RE = re.compile(r"\bArticles?\b")
ANNEX_KEYWORD_RE = re.compile(r"\bAnnex(?:es)?\b")
THIS_REGULATION_RE = re.compile(r"^\s*(?:of|under|in)\s+this\s+Regulation\b", re.IGNORECASE)
# Trailing short-name pattern (e.g., "Article 6 GDPR")
TRAILING_SHORT_NAME_RE = re.compile(r"^\s+(?:of\s+(?:the\s+)?)?(?P<name>[A-Za-z0-9 ]+?)\b")

# Article-list separators — recognised between article entries.
# "to", "–", "—" denote ranges; "," and "and" denote enumeration.
SEP_RE = re.compile(r"\s*(?:,|\band\b|\bto\b|–|—)\s*", re.IGNORECASE)

ROMAN_NUMERAL_RE = re.compile(r"^[IVXLCDM]+$")


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in " \t\n\r":
        pos += 1
    return pos


def _parse_pin_cite(text: str, pos: int) -> tuple[str | None, str | None, str | None, int]:
    """Parse optional (P)(L)(sub) tail. Returns (paragraph, letter, sub, end_pos)."""
    paragraph: str | None = None
    letter: str | None = None
    sub: str | None = None
    m = re.match(r"\s*\((\d+[a-z]?)\)", text[pos:])
    if m:
        paragraph = m.group(1)
        pos += m.end()
        m2 = re.match(r"\s*\(([a-z])\)", text[pos:])
        if m2:
            letter = m2.group(1)
            pos += m2.end()
            m3 = re.match(r"\s*\(([ivxlcdm]+)\)", text[pos:])
            if m3:
                sub = m3.group(1)
                pos += m3.end()
    return paragraph, letter, sub, pos


def _parse_article_entry(text: str, pos: int) -> tuple[dict | None, int]:
    """Parse a single article number + optional pin-cite. Returns (entry, end_pos)."""
    m = re.match(r"(\d+)([a-z])?", text[pos:])
    if not m:
        return None, pos
    target_article = m.group(1) + (m.group(2) or "")
    end = pos + m.end()
    paragraph, letter, sub, end = _parse_pin_cite(text, end)
    entry = {
        "target_article": target_article,
        "paragraph": paragraph,
        "letter": letter,
        "subparagraph": sub,
        "raw_span": (pos, end),
    }
    return entry, end


def _parse_article_list(text: str, pos: int) -> tuple[list[dict], int]:
    """Parse the run after "Article(s) ".

    Returns (entries, end_pos). Empty list if nothing parseable.
    Handles single, comma+and lists, ranges, and mixed.
    """
    pos = _skip_ws(text, pos)
    entries: list[dict] = []
    first, pos = _parse_article_entry(text, pos)
    if first is None:
        return [], pos
    entries.append(first)

    while pos < len(text):
        sep_m = SEP_RE.match(text[pos:])
        if not sep_m:
            break
        sep_text = sep_m.group(0).strip().lower()
        pos_after_sep = pos + sep_m.end()
        nxt, end_of_nxt = _parse_article_entry(text, pos_after_sep)
        if nxt is None:
            # Not really a continuation — leave separator unconsumed.
            break
        # Heuristic guard: if separator is "and"/"," and the previous entry had
        # NO pin-cite OR matching pin-cite shape, accept. If the next entry has
        # only digits (no pin-cite) and the previous had a pin-cite, still accept.
        if sep_text in ("to", "–", "—"):
            # Range expansion. Previous becomes start; next is end.
            try:
                start_n = int(re.match(r"\d+", entries[-1]["target_article"]).group(0))
                end_n = int(re.match(r"\d+", nxt["target_article"]).group(0))
            except Exception:
                start_n = end_n = None
            if start_n is not None and end_n is not None and end_n > start_n:
                # Cap absurd ranges (drafting typos / accidental matches).
                if end_n - start_n > 50:
                    break
                # Fill in start_n+1 .. end_n inclusive.
                for n in range(start_n + 1, end_n + 1):
                    entries.append(
                        {
                            "target_article": str(n),
                            "paragraph": None,
                            "letter": None,
                            "subparagraph": None,
                            "raw_span": (pos_after_sep, end_of_nxt),
                        }
                    )
                pos = end_of_nxt
                continue
            # Backwards or unparsable — just append the next as a normal entry.
            entries.append(nxt)
            pos = end_of_nxt
            continue
        # "and" / "," — append entry.
        entries.append(nxt)
        pos = end_of_nxt

    return entries, pos


def _classify_after(text: str, pos: int) -> tuple[str, dict]:
    """Look at text immediately after an article-list end to decide kind.

    Returns:
        (kind, info) where:
            kind in {"internal", "external_gdpr", "external_other", "internal_default"}
            info: { "celex": str | None, "official_name": str | None,
                    "short_name": str | None, "qualifier_span": (start, end) | None }

    "internal_default" means "no qualifier found, classify internal as fallback".
    """
    info: dict = {"celex": None, "official_name": None, "short_name": None, "qualifier_span": None}
    tail_start = pos
    tail_window = text[pos : pos + 220]

    # 1. "of this Regulation"
    m = THIS_REGULATION_RE.match(tail_window)
    if m:
        info["qualifier_span"] = (tail_start, tail_start + m.end())
        return "internal", info

    # 2. "of <instrument>" — we accept "of", "under", or "in" + maybe "the" + instrument
    of_m = re.match(r"\s*(?:of|under|in)\s+(?:the\s+)?", tail_window, re.IGNORECASE)
    rest_after_of = tail_window[of_m.end() :] if of_m else tail_window
    rest_offset = of_m.end() if of_m else 0

    # Try canonical instrument citations first.
    for pattern, _kind, extractor in INSTRUMENT_PATTERNS:
        im = pattern.match(rest_after_of)
        if im:
            celex, official = extractor(im)
            # AI Act self-citation collapses to internal — see AI_ACT_CELEX
            # comment near the top of this file.
            if celex == AI_ACT_CELEX:
                info["qualifier_span"] = (
                    tail_start + rest_offset,
                    tail_start + rest_offset + im.end(),
                )
                return "internal", info
            kind = "external_gdpr" if celex == GDPR_CELEX else "external_other"
            info["celex"] = celex
            info["official_name"] = official
            info["qualifier_span"] = (
                tail_start + rest_offset,
                tail_start + rest_offset + im.end(),
            )
            return kind, info

    # Try short-name aliases (only if there was an "of" / "under" / "in",
    # OR if the match is immediately adjacent — e.g., "Article 6 GDPR").
    # Two passes: with leading "of/under/in" and without.
    for surface in _SHORT_NAME_KEYS_BY_LEN:
        regex = re.compile(rf"\b{re.escape(surface)}\b", re.IGNORECASE)
        # First pass: check immediately after "of <the>?"
        if of_m:
            sm = regex.match(rest_after_of)
            if sm:
                celex, canon = SHORT_NAME_TO_CELEX[surface]
                kind = "external_gdpr" if celex == GDPR_CELEX else "external_other"
                info["celex"] = celex
                info["short_name"] = canon
                info["official_name"] = canon
                info["qualifier_span"] = (
                    tail_start + rest_offset,
                    tail_start + rest_offset + sm.end(),
                )
                return kind, info
        # Second pass: bare trailing short-name (with whitespace, no "of")
        bare_m = re.match(rf"\s+{regex.pattern}", tail_window)
        if bare_m:
            celex, canon = SHORT_NAME_TO_CELEX[surface]
            kind = "external_gdpr" if celex == GDPR_CELEX else "external_other"
            info["celex"] = celex
            info["short_name"] = canon
            info["official_name"] = canon
            info["qualifier_span"] = (tail_start, tail_start + bare_m.end())
            return kind, info

    # 3. No qualifier — default internal.
    return "internal_default", info


def _detect_standalone_instruments(text: str) -> list[dict]:
    """Find instrument citations NOT preceded by an article anchor.

    These are external references with target_article = None.
    We tag them so the coverage report can show instrument-only mentions
    (relevant for external_gdpr pages where "this Regulation refers to the
    GDPR" without picking out a specific article).
    """
    out: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()

    # Iterate canonical instrument patterns first.
    for pattern, _kind, extractor in INSTRUMENT_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            celex, official = extractor(m)
            # AI Act self-citations are NOT external — drop them entirely
            # from the standalone-instrument list (they'll surface elsewhere
            # if there's an actual article anchor preceding them).
            if celex == AI_ACT_CELEX:
                continue
            kind = "external_gdpr" if celex == GDPR_CELEX else "external_other"
            out.append(
                {
                    "raw": m.group(0),
                    "kind": kind,
                    "target_article": None,
                    "paragraph": None,
                    "letter": None,
                    "subparagraph": None,
                    "celex": celex,
                    "short_name": None,
                    "official_name": official,
                    "_span": span,
                }
            )
    # Short-name standalone mentions.
    for surface in _SHORT_NAME_KEYS_BY_LEN:
        regex = re.compile(rf"\b(?:the\s+)?{re.escape(surface)}\b", re.IGNORECASE)
        for m in regex.finditer(text):
            span = (m.start(), m.end())
            # Skip overlaps with already-recorded canonical spans.
            if any(s <= span[0] < e or s < span[1] <= e for (s, e) in seen_spans):
                continue
            seen_spans.add(span)
            celex, canon = SHORT_NAME_TO_CELEX[surface]
            kind = "external_gdpr" if celex == GDPR_CELEX else "external_other"
            out.append(
                {
                    "raw": m.group(0),
                    "kind": kind,
                    "target_article": None,
                    "paragraph": None,
                    "letter": None,
                    "subparagraph": None,
                    "celex": celex,
                    "short_name": canon,
                    "official_name": canon,
                    "_span": span,
                }
            )
    return out


def _parse_annex_entry(text: str, pos: int) -> tuple[dict | None, int]:
    """Parse a single Annex roman numeral, optional pin-cite. Returns (entry, end)."""
    pos = _skip_ws(text, pos)
    m = re.match(r"([IVXLCDM]+)\b", text[pos:])
    if not m:
        return None, pos
    annex_id = m.group(1)
    end = pos + m.end()
    paragraph, letter, sub, end = _parse_pin_cite(text, end)
    return (
        {
            "target_article": annex_id,
            "target_kind": "annex",
            "paragraph": paragraph,
            "letter": letter,
            "subparagraph": sub,
            "raw_span": (pos, end),
        },
        end,
    )


def _parse_annex_list(text: str, pos: int) -> tuple[list[dict], int]:
    """Parse Annex roman list. Mostly single ("Annex I") or pin-cite."""
    pos = _skip_ws(text, pos)
    entries: list[dict] = []
    first, pos = _parse_annex_entry(text, pos)
    if first is None:
        return [], pos
    entries.append(first)
    while pos < len(text):
        sep_m = SEP_RE.match(text[pos:])
        if not sep_m:
            break
        nxt, end_of_nxt = _parse_annex_entry(text, pos + sep_m.end())
        if nxt is None:
            break
        entries.append(nxt)
        pos = end_of_nxt
    return entries, pos


def _build_raw_string(text: str, anchor_start: int, list_end: int, qualifier_span: tuple[int, int] | None) -> str:
    """Reconstruct the raw source substring for the reference."""
    end = list_end
    if qualifier_span:
        end = qualifier_span[1]
    return text[anchor_start:end].strip()


# ─── Per-text reference extraction ─────────────────────────────────────


def extract_from_text(
    text: str,
    location: dict,
) -> list[dict]:
    """Extract all references from one text chunk.

    Returns a list of reference dicts (mixed internal + external + annex)
    with `kind` and `target_kind` fields populated. Each carries
    `location_in_source` (paragraph + letter), and `raw` for spot-checking.
    """
    refs: list[dict] = []
    handled_spans: set[tuple[int, int]] = set()

    # Phase 1: Article anchors with optional qualifier
    for anchor_m in ARTICLE_KEYWORD_RE.finditer(text):
        list_start = anchor_m.end()
        entries, list_end = _parse_article_list(text, list_start)
        if not entries:
            continue
        kind_label, info = _classify_after(text, list_end)
        if kind_label == "internal_default":
            classification = "internal"
        else:
            classification = kind_label

        raw = _build_raw_string(text, anchor_m.start(), list_end, info.get("qualifier_span"))

        for ent in entries:
            ref = {
                "raw": raw,
                "target_article": ent["target_article"],
                "paragraph": ent["paragraph"],
                "letter": ent["letter"],
                "subparagraph": ent["subparagraph"],
                "target_kind": "article",
                "kind": classification,
                "location_in_source": dict(location),
            }
            if classification != "internal":
                ref["celex"] = info.get("celex")
                ref["short_name"] = info.get("short_name")
                ref["official_name"] = info.get("official_name")
            refs.append(ref)
            handled_spans.add(tuple(ent["raw_span"]))
        # Also mark qualifier span handled to suppress duplicate
        # standalone-instrument detection for the same citation.
        if info.get("qualifier_span"):
            handled_spans.add(tuple(info["qualifier_span"]))

    # Phase 2: Annex anchors
    for anchor_m in ANNEX_KEYWORD_RE.finditer(text):
        list_start = anchor_m.end()
        entries, list_end = _parse_annex_list(text, list_start)
        if not entries:
            continue
        # Annexes are always internal in the AI Act.
        for ent in entries:
            refs.append(
                {
                    "raw": text[anchor_m.start() : list_end].strip(),
                    "target_article": ent["target_article"],
                    "paragraph": ent["paragraph"],
                    "letter": ent["letter"],
                    "subparagraph": ent["subparagraph"],
                    "target_kind": "annex",
                    "kind": "internal",
                    "location_in_source": dict(location),
                }
            )
            handled_spans.add(tuple(ent["raw_span"]))

    # Phase 3: Standalone instrument citations not already accounted for
    standalone = _detect_standalone_instruments(text)
    for s in standalone:
        span = s["_span"]
        # Skip if span overlaps with anything we already recorded.
        if any(hs[0] <= span[0] < hs[1] or hs[0] < span[1] <= hs[1] for hs in handled_spans):
            continue
        s2 = {k: v for k, v in s.items() if not k.startswith("_")}
        s2["target_kind"] = "instrument"
        s2["location_in_source"] = dict(location)
        refs.append(s2)

    return refs


# ─── Article iteration ─────────────────────────────────────────────────


def iter_text_chunks(article: dict):
    """Yield (text, location_dict) pairs for one article.

    For paragraphs with sub_points, scan each sub_point.text with letter set.
    For paragraphs without sub_points, scan para.text with letter=None.
    """
    for para in article.get("paragraphs", []):
        para_num = para.get("number")
        sub_points = para.get("sub_points") or []
        if sub_points:
            for sp in sub_points:
                label = (sp.get("label") or "").strip()
                # Strip parens from "(a)" → "a"
                letter = label.strip("()") or None
                yield sp.get("text", ""), {"paragraph": para_num, "letter": letter}
        else:
            yield para.get("text", ""), {"paragraph": para_num, "letter": None}


# ─── Aggregation ───────────────────────────────────────────────────────


def aggregate(articles: list[dict]) -> tuple[dict, dict, dict, dict]:
    """Walk articles and produce the three indexes plus a coverage breakdown.

    Returns:
        article_to_articles_internal  -> dict[str, list]
        article_to_external_refs      -> dict[str, list]
        articles_referencing          -> dict[str, list]
        coverage                      -> internal stats dict
    """
    internal_idx: dict[str, list[dict]] = defaultdict(list)
    external_idx: dict[str, list[dict]] = defaultdict(list)
    reverse_idx: dict[str, list[dict]] = defaultdict(list)

    coverage: dict = {
        "total_internal": 0,
        "total_external": 0,
        "by_kind": defaultdict(int),
        "by_target_kind": defaultdict(int),
        "by_celex": defaultdict(int),
        "per_source_article": defaultdict(int),
        "unparsed_patterns": [],
        "alias_hits": defaultdict(int),
    }

    for article in articles:
        src_num = str(article.get("number"))
        for text, location in iter_text_chunks(article):
            if not text:
                continue
            try:
                refs = extract_from_text(text, location)
            except Exception as exc:  # noqa: BLE001 — never let one article kill the run
                coverage["unparsed_patterns"].append(
                    {
                        "source_article": src_num,
                        "location": location,
                        "error": repr(exc),
                        "text_excerpt": text[:200],
                    }
                )
                continue
            for r in refs:
                # Filter out self-references at the source-article level (they
                # appear in drafting prose like "this Article" rarely; we don't
                # match those — but if a parser glitch emits a self-ref, drop
                # it).
                if r["kind"] == "internal" and r["target_kind"] == "article" and str(r["target_article"]) == src_num:
                    # Skip self-references; they are noise in a per-article
                    # index. The handoff doesn't forbid them but they offer
                    # zero rendering value.
                    continue
                if r["kind"] == "internal":
                    internal_idx[src_num].append(
                        {
                            "raw": r["raw"],
                            "target_article": r["target_article"],
                            "paragraph": r["paragraph"],
                            "letter": r["letter"],
                            "subparagraph": r["subparagraph"],
                            "target_kind": r["target_kind"],
                            "location_in_source": r["location_in_source"],
                        }
                    )
                    if r["target_kind"] == "article":
                        reverse_idx[str(r["target_article"])].append(
                            {
                                "raw": r["raw"],
                                "source_article": src_num,
                                "paragraph": r["paragraph"],
                                "letter": r["letter"],
                            }
                        )
                    coverage["total_internal"] += 1
                    coverage["by_target_kind"][r["target_kind"]] += 1
                else:
                    # external_*: collect in external_idx
                    external_idx[src_num].append(
                        {
                            "raw": r["raw"],
                            "kind": r["kind"],
                            "target_article": r["target_article"],
                            "paragraph": r["paragraph"],
                            "letter": r["letter"],
                            "subparagraph": r["subparagraph"],
                            "celex": r.get("celex"),
                            "short_name": r.get("short_name"),
                            "official_name": r.get("official_name"),
                            "target_kind": r.get("target_kind", "article"),
                            "location_in_source": r["location_in_source"],
                        }
                    )
                    coverage["total_external"] += 1
                    coverage["by_celex"][r.get("celex") or "(none)"] += 1
                    if r.get("short_name"):
                        coverage["alias_hits"][r["short_name"]] += 1

                coverage["by_kind"][r["kind"]] += 1
                coverage["per_source_article"][src_num] += 1

    # Deterministic ordering: sort each list by location-paragraph then raw.
    # Use a numeric extractor on `paragraph` and `target_article` so that
    # "Articles 8 to 15" expands with article 8 ahead of article 10 (string
    # sort would put '10' before '8'). The renderer takes the first entry
    # per unique raw; getting the smallest number first means a range
    # naturally links to its leftmost target.
    def _num_or_zero(s) -> int:
        if s is None:
            return 0
        m = re.match(r"\d+", str(s))
        return int(m.group(0)) if m else 0

    def _sort_key(item):
        loc = item.get("location_in_source") or {}
        return (
            _num_or_zero(loc.get("paragraph")),
            str(loc.get("letter") or ""),
            _num_or_zero(item.get("target_article")),
            str(item.get("target_article") or ""),
            item.get("raw", ""),
        )

    for k in internal_idx:
        internal_idx[k].sort(key=_sort_key)
    for k in external_idx:
        external_idx[k].sort(key=_sort_key)
    for k in reverse_idx:
        reverse_idx[k].sort(key=lambda x: (int(re.match(r"\d+", str(x["source_article"])).group(0)), x.get("raw", "")))

    return dict(internal_idx), dict(external_idx), dict(reverse_idx), coverage


# ─── I/O ───────────────────────────────────────────────────────────────


def write_json(path: Path, data) -> None:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def write_coverage_report(
    coverage: dict,
    internal_idx: dict,
    external_idx: dict,
    reverse_idx: dict,
    report_path: Path,
) -> None:
    lines: list[str] = []
    today = _dt.date.today().isoformat()
    lines.append(f"# Article References — Coverage Report ({today})")
    lines.append("")
    lines.append("Generated by `scripts/extract_article_references.py` (Step 4.9a).")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total internal references: **{coverage['total_internal']}**")
    lines.append(f"- Total external references: **{coverage['total_external']}**")
    lines.append(f"- Articles with internal refs:  {len(internal_idx)} / 113")
    lines.append(f"- Articles with external refs:  {len(external_idx)} / 113")
    lines.append(f"- Articles cited (reverse idx): {len(reverse_idx)} / 113")
    lines.append("")
    lines.append("## Breakdown by kind")
    lines.append("")
    lines.append("| Kind | Count |")
    lines.append("|------|-------|")
    for k, v in sorted(coverage["by_kind"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{k}` | {v} |")
    lines.append("")
    lines.append("## Breakdown by target kind (internal only)")
    lines.append("")
    lines.append("| Target kind | Count |")
    lines.append("|-------------|-------|")
    for k, v in sorted(coverage["by_target_kind"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{k}` | {v} |")
    lines.append("")
    lines.append("## Breakdown by external instrument (CELEX)")
    lines.append("")
    lines.append("| CELEX | Count |")
    lines.append("|-------|-------|")
    for k, v in sorted(coverage["by_celex"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{k}` | {v} |")
    lines.append("")
    lines.append("## Alias-table hits")
    lines.append("")
    if coverage["alias_hits"]:
        lines.append("| Short name | Count |")
        lines.append("|------------|-------|")
        for k, v in sorted(coverage["alias_hits"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{k}` | {v} |")
    else:
        lines.append("_None._")
    lines.append("")
    lines.append("## Top 20 source articles by reference count")
    lines.append("")
    lines.append("| Article | Count |")
    lines.append("|---------|-------|")
    top20 = sorted(
        coverage["per_source_article"].items(),
        key=lambda kv: -kv[1],
    )[:20]
    for art, count in top20:
        lines.append(f"| {art} | {count} |")
    lines.append("")
    lines.append("## Unparsed patterns (sampling)")
    lines.append("")
    if coverage["unparsed_patterns"]:
        for entry in coverage["unparsed_patterns"][:50]:
            lines.append(
                f"- Article {entry['source_article']} (para {entry['location'].get('paragraph')}, letter {entry['location'].get('letter')}): {entry.get('error')}"
            )
            lines.append(f"  > {entry['text_excerpt'][:160]}")
    else:
        lines.append("_No errors trapped during parsing._")
    lines.append("")
    lines.append("## Spot-check: first 5 internal references from Article 2")
    lines.append("")
    art2_internal = internal_idx.get("2") or []
    if art2_internal:
        for ref in art2_internal[:5]:
            lines.append(f"- raw=`{ref['raw']}` → article {ref['target_article']}({ref.get('paragraph')})({ref.get('letter')})")
    else:
        lines.append("_(no internal refs collected for Article 2)_")
    lines.append("")
    lines.append("## Spot-check: first 5 external references from Article 2")
    lines.append("")
    art2_external = external_idx.get("2") or []
    if art2_external:
        for ref in art2_external[:5]:
            lines.append(f"- raw=`{ref['raw']}` → CELEX {ref.get('celex')} ({ref.get('kind')})")
    else:
        lines.append("_(no external refs collected for Article 2)_")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report regenerated on every `extract_article_references.py` run.*")

    report_path.write_text("\n".join(lines), encoding="utf-8")


# ─── Driver ────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument(
        "--report-only",
        action="store_true",
        help="Compute everything but skip writing cross_references.json (debug mode).",
    )
    args = ap.parse_args()

    if not SRC_ARTICLES.exists():
        print(f"FATAL: {SRC_ARTICLES} not found", file=sys.stderr)
        return 1
    if not SRC_CROSS_REFS.exists():
        print(f"FATAL: {SRC_CROSS_REFS} not found", file=sys.stderr)
        return 1

    articles = json.loads(SRC_ARTICLES.read_text(encoding="utf-8"))
    cross = json.loads(SRC_CROSS_REFS.read_text(encoding="utf-8"))

    # Sanity: existing keys must be present.
    if "article_to_recitals" not in cross or "recital_to_articles" not in cross:
        print("FATAL: existing cross_references.json missing one of "
              "{article_to_recitals, recital_to_articles}", file=sys.stderr)
        return 2


    internal_idx, external_idx, reverse_idx, coverage = aggregate(articles)

    # Merge new keys without dropping existing ones.
    cross["article_to_articles_internal"] = internal_idx
    cross["article_to_external_refs"] = external_idx
    cross["articles_referencing"] = reverse_idx

    if not args.report_only:
        write_json(SRC_CROSS_REFS, cross)

    CTRL_ROOM_REF.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    report_path = CTRL_ROOM_REF / f"article-references-coverage-{today}.md"
    write_coverage_report(coverage, internal_idx, external_idx, reverse_idx, report_path)

    print(f"OK -- internal={coverage['total_internal']} external={coverage['total_external']}")
    print(f"  source articles with internal refs : {len(internal_idx)}")
    print(f"  source articles with external refs : {len(external_idx)}")
    print(f"  target articles referenced (reverse): {len(reverse_idx)}")
    print(f"  coverage report                    : {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
