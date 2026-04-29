#!/usr/bin/env python3
"""
build_drafting_history.py — Step 4.4 bilingual drafting-history bridge.

Inputs
------
- `english-intermediate/_legacy/drafting_history_en_pre_4.4.json` — frozen archive of the
  pre-4.4 EN drafting-history blob. We KEEP commission-2021/{articles,recitals} only.
  parliament-2023 entries are parser garbage (4.4 coverage analysis §4.1) and final-2024
  is redundant with the live regulation (Q B). Both are dropped here; do NOT round-trip them.
  This file is the script's authoritative input for the legacy commission-2021 EN data and
  is never overwritten by this script. Restored from git on 2026-04-28 to keep this script
  idempotent (the original src/data/drafting_history_en.json is the *output* path).
- `dutch-intermediate/history/commission-2021/{articles,recitals,annexes}/*.json` — clean NL
  commission-2021 corpus (4.3a output). Per-file JSONs with body_md/body_text.
- `english-intermediate/history/parliament-2023/amendments/*.json` — clean EN amendments
  (4.3c output). 771 entries, parallel in shape to NL.
- `dutch-intermediate/history/parliament-2023/amendments/*.json` — NL amendments (4.3a output).

Outputs
-------
- `src/data/drafting_history_en.json` — REWRITTEN.
- `src/data/drafting_history_nl.json` — NEW.

Schema
------
Both files share shape:

    {
      "stages": [
        {"id", "label_en", "label_nl", "date", "source_label", "order"},
        ...
      ],
      "snapshots": [
        {"snapshot_id", "stage", "content_type", "number", "title", "text",
         (amendments only): "amends_kind", "amends_number", "amends_paragraph",
                            "amends_suffix", "amends_target_text"},
        ...
      ]
    }

`content_type ∈ {'articles', 'recitals', 'annexes', 'amendments'}`.
`amends_kind ∈ {'article', 'recital', 'annex', 'structural'}` for amendments only.

Snapshot IDs are deterministic, derived from `(stage, content_type, number)`. Sort order
of `snapshots[]` is `(stage.order, content_type_rank, number_numeric_key, number)` — stable
across rebuilds. Re-running the script must produce byte-identical output.

This script is the 4.4 bridge step. Asserts loud on count mismatches.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# ─── Paths ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
SRC_DATA = ROOT / "src" / "data"
DUTCH_INT = ROOT / "dutch-intermediate"
ENGLISH_INT = ROOT / "english-intermediate"

LEGACY_EN_BLOB = ENGLISH_INT / "_legacy" / "drafting_history_en_pre_4.4.json"
OUT_EN = SRC_DATA / "drafting_history_en.json"
OUT_NL = SRC_DATA / "drafting_history_nl.json"

# ─── Stage metadata ───────────────────────────────────────────────────────

# final-2024 deliberately omitted: the "Final adopted text" card in the
# timeline reads from articles_{en,nl}.json directly (Q B resolution).
STAGES: list[dict[str, Any]] = [
    {
        "id": "commission-2021",
        "label_en": "Commission Proposal",
        "label_nl": "Commissievoorstel",
        "date": "2021-04-21",
        "source_label": "COM(2021) 206 final",
        "order": 1,
    },
    {
        "id": "parliament-2023",
        "label_en": "European Parliament Mandate",
        "label_nl": "Standpunt van het Europees Parlement",
        "date": "2023-06-14",
        "source_label": "P9_TA(2023)0236",
        "order": 2,
    },
]

CONTENT_TYPE_RANK = {"articles": 1, "recitals": 2, "annexes": 3, "amendments": 4}

# ─── Number sort helpers ──────────────────────────────────────────────────

ROMAN_ORDER = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
    "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
}


def num_key(s: str) -> tuple[int, str]:
    """Sort key: leading-int, then full string. Stable for keys like "60a"."""
    m = re.match(r"(\d+)", str(s))
    return (int(m.group(1)) if m else 0, str(s))


def roman_key(s: str) -> tuple[int, str]:
    """Sort key for roman numerals (annexes)."""
    return (ROMAN_ORDER.get(str(s).upper(), 999), str(s))


# ─── Amendment target classifier ──────────────────────────────────────────

# Per 4.3c completion notes §7: case-insensitive, em-dash variant, structural keywords.
# EN classifier
RE_EN_ARTICLE = re.compile(
    r"\bArticle\s*[—–-]?\s*(\d+)\s*([a-z])?\b",
    re.IGNORECASE,
)
RE_EN_PARAGRAPH = re.compile(
    r"\b(?:paragraph|point|subparagraph)\s+([\d.]+)\s*([a-z])?\b",
    re.IGNORECASE,
)
RE_EN_RECITAL = re.compile(r"\bRecital\s+(\d+)\s*([a-z])?\b", re.IGNORECASE)
RE_EN_ANNEX = re.compile(r"\bAnnex\s+([IVX]+)\b", re.IGNORECASE)
RE_EN_STRUCTURAL = re.compile(
    r"\b(Citation|Title|Chapter|Section)\b", re.IGNORECASE
)

# NL classifier
RE_NL_ARTICLE = re.compile(r"\bArtikel\s*[—–-]?\s*(\d+)\s*([a-z])?\b", re.IGNORECASE)
NL_SUFFIX_WORDS = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies)"
RE_NL_ARTICLE_SUFFIX = re.compile(rf"\bArtikel\s+\d+\s+({NL_SUFFIX_WORDS})\b", re.IGNORECASE)
RE_NL_PARAGRAPH = re.compile(
    rf"\b(?:lid|alinea|punt)\s+([\d.]+)(?:\s+({NL_SUFFIX_WORDS}|[a-z]))?\b",
    re.IGNORECASE,
)
RE_NL_RECITAL = re.compile(rf"\bOverweging\s+(\d+)(?:\s+({NL_SUFFIX_WORDS}|[a-z]))?\b", re.IGNORECASE)
RE_NL_ANNEX = re.compile(r"\bBijlage\s+([IVX]+)\b", re.IGNORECASE)
RE_NL_STRUCTURAL = re.compile(
    r"\b(Visum|Titel|Hoofdstuk|Deel)\b", re.IGNORECASE
)


def classify_amendment(target: str, lang: str) -> dict[str, Any]:
    """Parse the EUR-Lex amendment_target string into amends_* fields.

    Returns one of:
      {amends_kind: 'article', amends_number, amends_suffix?, amends_paragraph?}
      {amends_kind: 'recital', amends_number, amends_suffix?}
      {amends_kind: 'annex', amends_number}
      {amends_kind: 'structural'}
    Plus always: {amends_target_text: <raw target>}.
    """
    base: dict[str, Any] = {"amends_target_text": target}

    if lang == "en":
        m_art = RE_EN_ARTICLE.search(target)
        if m_art:
            out: dict[str, Any] = {**base, "amends_kind": "article", "amends_number": m_art.group(1)}
            if m_art.group(2):
                out["amends_suffix"] = m_art.group(2).lower()
            m_para = RE_EN_PARAGRAPH.search(target)
            if m_para:
                out["amends_paragraph"] = m_para.group(1)
                if m_para.group(2):
                    out["amends_paragraph_suffix"] = m_para.group(2).lower()
            return out
        m_rec = RE_EN_RECITAL.search(target)
        if m_rec:
            out = {**base, "amends_kind": "recital", "amends_number": m_rec.group(1)}
            if m_rec.group(2):
                out["amends_suffix"] = m_rec.group(2).lower()
            return out
        m_ann = RE_EN_ANNEX.search(target)
        if m_ann:
            return {**base, "amends_kind": "annex", "amends_number": m_ann.group(1).upper()}
        if RE_EN_STRUCTURAL.search(target):
            return {**base, "amends_kind": "structural"}
        return {**base, "amends_kind": "structural"}  # unknowns bucket as structural

    if lang == "nl":
        m_art = RE_NL_ARTICLE.search(target)
        if m_art:
            out = {**base, "amends_kind": "article", "amends_number": m_art.group(1)}
            if m_art.group(2):
                out["amends_suffix"] = m_art.group(2).lower()
            else:
                m_suf = RE_NL_ARTICLE_SUFFIX.search(target)
                if m_suf:
                    out["amends_suffix"] = m_suf.group(1).lower()
            m_para = RE_NL_PARAGRAPH.search(target)
            if m_para:
                out["amends_paragraph"] = m_para.group(1)
                if m_para.group(2):
                    out["amends_paragraph_suffix"] = m_para.group(2).lower()
            return out
        m_rec = RE_NL_RECITAL.search(target)
        if m_rec:
            out = {**base, "amends_kind": "recital", "amends_number": m_rec.group(1)}
            if m_rec.group(2):
                out["amends_suffix"] = m_rec.group(2).lower()
            return out
        m_ann = RE_NL_ANNEX.search(target)
        if m_ann:
            return {**base, "amends_kind": "annex", "amends_number": m_ann.group(1).upper()}
        if RE_NL_STRUCTURAL.search(target):
            return {**base, "amends_kind": "structural"}
        return {**base, "amends_kind": "structural"}

    raise ValueError(f"unknown lang {lang!r}")


# ─── Snapshot ID ──────────────────────────────────────────────────────────


def snapshot_id(stage: str, content_type: str, number: str) -> str:
    safe_num = str(number).lower().replace(" ", "")
    singular = {"articles": "article", "recitals": "recital", "annexes": "annex", "amendments": "amendment"}[content_type]
    return f"snap_{stage}_{singular}_{safe_num}"


# ─── Sort snapshots ───────────────────────────────────────────────────────


def sort_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stage_order = {s["id"]: s["order"] for s in STAGES}

    def key(s: dict[str, Any]) -> tuple[int, int, int, str]:
        ct_rank = CONTENT_TYPE_RANK.get(s["content_type"], 99)
        if s["content_type"] == "annexes":
            n_key = roman_key(s["number"])
        else:
            n_key = num_key(s["number"])
        return (stage_order.get(s["stage"], 99), ct_rank, n_key[0], str(s["number"]))

    return sorted(snapshots, key=key)


# ─── EN commission-2021 ingest (from legacy blob) ─────────────────────────


def load_legacy_en() -> dict[str, dict[str, Any]]:
    """Returns by_version[stage][content_type] for commission-2021 only.

    We deliberately discard parliament-2023 (parser garbage) and final-2024
    (redundant with live regulation) per coverage analysis §4.1, §4.2 and Q B.
    """
    raw = json.loads(LEGACY_EN_BLOB.read_text(encoding="utf-8"))
    return raw["by_version"]


def en_commission_snapshots(legacy_by_version: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    com = legacy_by_version.get("commission-2021", {})
    for num, row in com.get("articles", {}).items():
        body = row.get("body", "") if isinstance(row, dict) else str(row)
        title = row.get("title") if isinstance(row, dict) else None
        out.append({
            "snapshot_id": snapshot_id("commission-2021", "articles", str(num)),
            "stage": "commission-2021",
            "content_type": "articles",
            "number": str(num),
            "title": title,
            "text": body,
        })
    for num, row in com.get("recitals", {}).items():
        body = row.get("body", "") if isinstance(row, dict) else str(row)
        out.append({
            "snapshot_id": snapshot_id("commission-2021", "recitals", str(num)),
            "stage": "commission-2021",
            "content_type": "recitals",
            "number": str(num),
            "title": None,
            "text": body,
        })
    # EN has no annexes branch in any stage of the legacy blob — coverage report §4.
    return out


# ─── NL commission-2021 ingest (from intermediate per-file JSONs) ─────────


def nl_commission_snapshots() -> list[dict[str, Any]]:
    base = DUTCH_INT / "history" / "commission-2021"
    out: list[dict[str, Any]] = []

    for f in sorted((base / "articles").glob("article-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append({
            "snapshot_id": snapshot_id("commission-2021", "articles", d["article_number"]),
            "stage": "commission-2021",
            "content_type": "articles",
            "number": str(d["article_number"]),
            "title": d.get("article_title"),
            "text": d.get("body_text") or d.get("body_md") or "",
        })

    for f in sorted((base / "recitals").glob("recital-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append({
            "snapshot_id": snapshot_id("commission-2021", "recitals", d["recital_number"]),
            "stage": "commission-2021",
            "content_type": "recitals",
            "number": str(d["recital_number"]),
            "title": None,
            "text": d.get("body_text") or d.get("body_md") or "",
        })

    for f in sorted((base / "annexes").glob("annex-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        roman = d["annex_number_roman"]
        out.append({
            "snapshot_id": snapshot_id("commission-2021", "annexes", roman.lower()),
            "stage": "commission-2021",
            "content_type": "annexes",
            "number": roman,
            "title": d.get("annex_title"),
            "text": d.get("body_text") or d.get("body_md") or "",
        })

    return out


# ─── Parliament-2023 amendments (both languages) ──────────────────────────


def amendment_snapshots(intermediate_root: Path, lang: str) -> list[dict[str, Any]]:
    base = intermediate_root / "history" / "parliament-2023" / "amendments"
    out: list[dict[str, Any]] = []
    for f in sorted(base.glob("amendment-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        target = d.get("amendment_target", "")
        amends = classify_amendment(target, lang)
        snap: dict[str, Any] = {
            "snapshot_id": snapshot_id("parliament-2023", "amendments", d["amendment_number"]),
            "stage": "parliament-2023",
            "content_type": "amendments",
            "number": str(d["amendment_number"]),
            "title": target,
            "text": d.get("body_md") or "",
        }
        snap.update(amends)
        out.append(snap)
    return out


# ─── Build per-language file ──────────────────────────────────────────────


def build_lang(lang: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_snaps = sort_snapshots(snapshots)
    return {
        "stages": list(STAGES),
        "snapshots": sorted_snaps,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    s = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
    path.write_text(s + "\n", encoding="utf-8")


# ─── Main ─────────────────────────────────────────────────────────────────


def main() -> int:
    print("[build_drafting_history] reading inputs", flush=True)
    legacy_en = load_legacy_en()

    en_com = en_commission_snapshots(legacy_en)
    en_amend = amendment_snapshots(ENGLISH_INT, "en")
    en_snaps = en_com + en_amend

    nl_com = nl_commission_snapshots()
    nl_amend = amendment_snapshots(DUTCH_INT, "nl")
    nl_snaps = nl_com + nl_amend

    # Assertions — fail loud on regressions.
    en_com_articles = [s for s in en_com if s["content_type"] == "articles"]
    en_com_recitals = [s for s in en_com if s["content_type"] == "recitals"]
    en_com_annexes  = [s for s in en_com if s["content_type"] == "annexes"]
    nl_com_articles = [s for s in nl_com if s["content_type"] == "articles"]
    nl_com_recitals = [s for s in nl_com if s["content_type"] == "recitals"]
    nl_com_annexes  = [s for s in nl_com if s["content_type"] == "annexes"]

    assert len(en_com_articles) == 84, f"EN commission-2021 articles: expected 84, got {len(en_com_articles)}"
    assert len(en_com_recitals) == 70, f"EN commission-2021 recitals: expected 70, got {len(en_com_recitals)}"
    assert len(en_com_annexes)  == 0,  f"EN commission-2021 annexes: expected 0, got {len(en_com_annexes)}"
    assert len(nl_com_articles) == 85, f"NL commission-2021 articles: expected 85, got {len(nl_com_articles)}"
    assert len(nl_com_recitals) == 89, f"NL commission-2021 recitals: expected 89, got {len(nl_com_recitals)}"
    assert len(nl_com_annexes)  == 9,  f"NL commission-2021 annexes: expected 9, got {len(nl_com_annexes)}"
    assert len(en_amend) == 771, f"EN parliament-2023 amendments: expected 771, got {len(en_amend)}"
    assert len(nl_amend) == 771, f"NL parliament-2023 amendments: expected 771, got {len(nl_amend)}"

    # Sanity: snapshot_id uniqueness within each language.
    for lang_label, snaps in (("EN", en_snaps), ("NL", nl_snaps)):
        ids = [s["snapshot_id"] for s in snaps]
        if len(ids) != len(set(ids)):
            dup = [i for i in ids if ids.count(i) > 1]
            raise AssertionError(f"{lang_label}: duplicate snapshot_ids: {dup[:5]}")

    en_payload = build_lang("en", en_snaps)
    nl_payload = build_lang("nl", nl_snaps)

    OUT_EN.parent.mkdir(parents=True, exist_ok=True)
    write_json(OUT_EN, en_payload)
    write_json(OUT_NL, nl_payload)

    print(f"[build_drafting_history] EN: {len(en_snaps)} snapshots → {OUT_EN.relative_to(ROOT)}")
    print(f"  commission-2021: articles={len(en_com_articles)} recitals={len(en_com_recitals)} annexes=0")
    print(f"  parliament-2023: amendments={len(en_amend)}")
    print(f"[build_drafting_history] NL: {len(nl_snaps)} snapshots → {OUT_NL.relative_to(ROOT)}")
    print(f"  commission-2021: articles={len(nl_com_articles)} recitals={len(nl_com_recitals)} annexes={len(nl_com_annexes)}")
    print(f"  parliament-2023: amendments={len(nl_amend)}")

    # Amends-distribution summary (informational; not asserted).
    # Amends-distribution summary (informational; not asserted).
    en_kinds: dict[str, int] = {}
    for s in en_amend:
        k = s.get("amends_kind", "?")
        en_kinds[k] = en_kinds.get(k, 0) + 1
    nl_kinds: dict[str, int] = {}
    for s in nl_amend:
        k = s.get("amends_kind", "?")
        nl_kinds[k] = nl_kinds.get(k, 0) + 1
    print(f"[build_drafting_history] EN amendment classification: {en_kinds}")
    print(f"[build_drafting_history] NL amendment classification: {nl_kinds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
