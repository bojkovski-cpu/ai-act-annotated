#!/usr/bin/env python3
"""
verify_parity.py — Deterministic EN/NL parity verifier for the AI Act
Annotated Edition data layer.

Step 4.6, v1.1.

Reads the per-language regulation, drafting-history, omnibus, cross-reference,
and (optional) guidance JSON blobs and asserts every parity rule in
control-room/reference/parity-asymmetry-catalogue-YYYY-MM-DD.md.

The catalogue distinguishes "strict parity" (asymmetry = bug) from "expected
asymmetry" (catalogued) and from "soft-flag" (record but don't fail).

Outputs:
  - stdout: human-readable PASS/FAIL line per check.
  - stderr (only when --json-errors and there are unexpected failures):
        a single-line JSON array of unexpected-asymmetry records.
  - exit code:
        0  all strict checks PASS, all expected asymmetries match catalogue
        1  at least one unexpected asymmetry
        2  a required data file is missing or malformed

Usage:
    python scripts/verify_parity.py
    python scripts/verify_parity.py --report control-room/reference/parity-report-2026-04-28.md
    python scripts/verify_parity.py --no-dist           # skip optional dist/ checks
    python scripts/verify_parity.py --json-errors

The verifier is read-only with respect to the data layer. It writes only the
markdown report when --report is supplied (and only outside src/data/).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# scripts/ is at <repo>/scripts/, so repo root is one level up.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "src" / "data"
DIST_DIR = REPO_ROOT / "dist"

# Catalogue lives outside the repo (control-room is outside the git tree).
# Resolve by walking up until we find a sibling "control-room" or by an
# explicit override.
def _find_control_room() -> Optional[Path]:
    here = REPO_ROOT
    for candidate in [here.parent, here.parent.parent, here]:
        cr = candidate / "control-room"
        if cr.is_dir():
            return cr
    return None

CONTROL_ROOM = _find_control_room()

# Regulation strict-parity targets
EXPECTED_ARTICLES = 113
EXPECTED_RECITALS = 180
EXPECTED_ANNEXES = 13

# Drafting-history catalogued counts (commission-2021 stage)
EXPECTED_COM2021 = {
    "en": {"articles": 84, "recitals": 70, "annexes": 0},
    "nl": {"articles": 85, "recitals": 89, "annexes": 9},
}
# parliament-2023 stage: amendments must be symmetric
EXPECTED_PARL2023_AMENDMENTS = 771

# CELEX regex for external references (if 4.9b ships during 4.6)
CELEX_RE = re.compile(r"^3\d{4}[RLDC]\d{4}$")
GDPR_CELEX = "32016R0679"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    status: str           # "PASS" | "FAIL" | "SOFT" | "SKIP"
    detail: str = ""
    expected: Any = None
    actual: Any = None

    @property
    def is_unexpected_fail(self) -> bool:
        return self.status == "FAIL"


@dataclass
class Verifier:
    data_dir: Path
    dist_dir: Optional[Path]
    catalogue_path: Optional[Path]
    results: List[CheckResult] = field(default_factory=list)
    fatal_load_error: bool = False

    # Caches
    articles_en: List[Dict[str, Any]] = field(default_factory=list)
    articles_nl: List[Dict[str, Any]] = field(default_factory=list)
    recitals_en: List[Dict[str, Any]] = field(default_factory=list)
    recitals_nl: List[Dict[str, Any]] = field(default_factory=list)
    annexes_en: List[Dict[str, Any]] = field(default_factory=list)
    annexes_nl: List[Dict[str, Any]] = field(default_factory=list)
    drafting_en: Dict[str, Any] = field(default_factory=dict)
    drafting_nl: Dict[str, Any] = field(default_factory=dict)
    omnibus_en: List[Dict[str, Any]] = field(default_factory=list)
    cross_refs: Dict[str, Any] = field(default_factory=dict)
    guidance: Optional[List[Dict[str, Any]]] = None
    omnibus_nl_present: bool = False

    # ----- helpers --------------------------------------------------------

    def _load_json(self, name: str, required: bool = True) -> Any:
        path = self.data_dir / name
        if not path.exists():
            if required:
                self.results.append(CheckResult(
                    name=f"load:{name}",
                    status="FAIL",
                    detail=f"Required file missing: {path}",
                ))
                self.fatal_load_error = True
                return None
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self.results.append(CheckResult(
                name=f"load:{name}",
                status="FAIL",
                detail=f"Malformed JSON: {exc}",
            ))
            self.fatal_load_error = True
            return None

    def _add(self, name: str, status: str, detail: str = "",
             expected: Any = None, actual: Any = None) -> None:
        self.results.append(CheckResult(
            name=name, status=status, detail=detail,
            expected=expected, actual=actual,
        ))

    # ----- load all inputs ------------------------------------------------

    def load_all(self) -> None:
        self.articles_en = self._load_json("articles_en.json") or []
        self.articles_nl = self._load_json("articles_nl.json") or []
        self.recitals_en = self._load_json("recitals_en.json") or []
        self.recitals_nl = self._load_json("recitals_nl.json") or []
        self.annexes_en = self._load_json("annexes_en.json") or []
        self.annexes_nl = self._load_json("annexes_nl.json") or []
        self.drafting_en = self._load_json("drafting_history_en.json") or {}
        self.drafting_nl = self._load_json("drafting_history_nl.json") or {}
        self.omnibus_en = self._load_json("omnibus_amendments_en.json") or []
        self.cross_refs = self._load_json("cross_references.json") or {}
        # Optional: guidance.json, omnibus_amendments_nl.json
        self.guidance = self._load_json("guidance.json", required=False)
        omnibus_nl_path = self.data_dir / "omnibus_amendments_nl.json"
        self.omnibus_nl_present = omnibus_nl_path.exists()

    # ----- strict parity: regulation text --------------------------------

    def check_count_parity(self) -> None:
        for label, expected, en, nl in [
            ("articles", EXPECTED_ARTICLES, self.articles_en, self.articles_nl),
            ("recitals", EXPECTED_RECITALS, self.recitals_en, self.recitals_nl),
            ("annexes",  EXPECTED_ANNEXES,  self.annexes_en,  self.annexes_nl),
        ]:
            ok = len(en) == expected == len(nl)
            self._add(
                name=f"count_parity:{label}",
                status="PASS" if ok else "FAIL",
                detail=f"EN={len(en)} NL={len(nl)} expected={expected}",
                expected=expected,
                actual={"en": len(en), "nl": len(nl)},
            )

    def check_id_set_parity(self) -> None:
        en_a = sorted(str(a["number"]) for a in self.articles_en)
        nl_a = sorted(str(a["number"]) for a in self.articles_nl)
        diff_en = sorted(set(en_a) - set(nl_a))
        diff_nl = sorted(set(nl_a) - set(en_a))
        self._add(
            name="id_set_parity:articles",
            status="PASS" if not diff_en and not diff_nl else "FAIL",
            detail=f"missing_in_NL={diff_en} missing_in_EN={diff_nl}",
        )
        en_r = sorted(str(r["number"]) for r in self.recitals_en)
        nl_r = sorted(str(r["number"]) for r in self.recitals_nl)
        diff_en_r = sorted(set(en_r) - set(nl_r))
        diff_nl_r = sorted(set(nl_r) - set(en_r))
        self._add(
            name="id_set_parity:recitals",
            status="PASS" if not diff_en_r and not diff_nl_r else "FAIL",
            detail=f"missing_in_NL={diff_en_r} missing_in_EN={diff_nl_r}",
        )
        en_x = sorted(str(a["id"]) for a in self.annexes_en)
        nl_x = sorted(str(a["id"]) for a in self.annexes_nl)
        diff_en_x = sorted(set(en_x) - set(nl_x))
        diff_nl_x = sorted(set(nl_x) - set(en_x))
        self._add(
            name="id_set_parity:annexes",
            status="PASS" if not diff_en_x and not diff_nl_x else "FAIL",
            detail=f"missing_in_NL={diff_en_x} missing_in_EN={diff_nl_x}",
        )

    def check_field_parity_articles(self) -> None:
        en_by = {str(a["number"]): a for a in self.articles_en}
        nl_by = {str(a["number"]): a for a in self.articles_nl}
        common = sorted(set(en_by) & set(nl_by), key=lambda x: int(x) if x.isdigit() else 9999)
        mism = []
        for n in common:
            e, l = en_by[n], nl_by[n]
            for fld in ("chapter", "chapter_roman"):
                if str(e.get(fld)) != str(l.get(fld)):
                    mism.append((n, fld, e.get(fld), l.get(fld)))
        self._add(
            name="field_parity:articles[chapter,chapter_roman]",
            status="PASS" if not mism else "FAIL",
            detail=f"mismatches={len(mism)}; sample={mism[:3]}",
        )
        # chapter_title: must be non-empty in BOTH languages, but values legitimately differ
        empty = [n for n in common
                 if not (en_by[n].get("chapter_title") and nl_by[n].get("chapter_title"))]
        self._add(
            name="field_presence:articles[chapter_title]",
            status="PASS" if not empty else "FAIL",
            detail=f"articles missing chapter_title: {empty[:5]}",
        )

    # ----- drafting history vs catalogue ---------------------------------

    @staticmethod
    def _drafting_counts(blob: Dict[str, Any]) -> Dict[Tuple[str, str], int]:
        counts: Dict[Tuple[str, str], int] = {}
        for s in blob.get("snapshots", []):
            key = (s.get("stage"), s.get("content_type"))
            counts[key] = counts.get(key, 0) + 1
        return counts

    def check_drafting_history(self) -> None:
        en_counts = self._drafting_counts(self.drafting_en)
        nl_counts = self._drafting_counts(self.drafting_nl)

        # commission-2021 — must match catalogue
        for ct, exp_en in EXPECTED_COM2021["en"].items():
            actual = en_counts.get(("commission-2021", ct), 0)
            ok = actual == exp_en
            self._add(
                name=f"drafting_history:commission-2021/EN/{ct}",
                status="PASS" if ok else "FAIL",
                detail=f"expected={exp_en} actual={actual}",
                expected=exp_en, actual=actual,
            )
        for ct, exp_nl in EXPECTED_COM2021["nl"].items():
            actual = nl_counts.get(("commission-2021", ct), 0)
            ok = actual == exp_nl
            self._add(
                name=f"drafting_history:commission-2021/NL/{ct}",
                status="PASS" if ok else "FAIL",
                detail=f"expected={exp_nl} actual={actual}",
                expected=exp_nl, actual=actual,
            )

        # parliament-2023 — both must be 771 amendments, 0 articles/recitals/annexes
        for lang, blob_counts in (("en", en_counts), ("nl", nl_counts)):
            for ct in ("articles", "recitals", "annexes"):
                actual = blob_counts.get(("parliament-2023", ct), 0)
                self._add(
                    name=f"drafting_history:parliament-2023/{lang.upper()}/{ct}",
                    status="PASS" if actual == 0 else "FAIL",
                    detail=f"expected=0 actual={actual}",
                )
            actual = blob_counts.get(("parliament-2023", "amendments"), 0)
            self._add(
                name=f"drafting_history:parliament-2023/{lang.upper()}/amendments",
                status="PASS" if actual == EXPECTED_PARL2023_AMENDMENTS else "FAIL",
                detail=f"expected={EXPECTED_PARL2023_AMENDMENTS} actual={actual}",
            )

        # final-2024 must NOT exist as a stage in either file
        for lang, blob in (("en", self.drafting_en), ("nl", self.drafting_nl)):
            stage_ids = [s.get("id") for s in blob.get("stages", [])]
            has_final = "final-2024" in stage_ids
            self._add(
                name=f"drafting_history:final-2024_absent/{lang.upper()}",
                status="PASS" if not has_final else "FAIL",
                detail=f"stages={stage_ids}",
            )
            # And no snapshots tagged final-2024
            snaps_with_final = sum(
                1 for s in blob.get("snapshots", [])
                if s.get("stage") == "final-2024"
            )
            self._add(
                name=f"drafting_history:final-2024_no_snapshots/{lang.upper()}",
                status="PASS" if snaps_with_final == 0 else "FAIL",
                detail=f"snapshots_with_final-2024={snaps_with_final}",
            )

        # snapshot_id uniqueness within each language
        for lang, blob in (("en", self.drafting_en), ("nl", self.drafting_nl)):
            ids = [s.get("snapshot_id") for s in blob.get("snapshots", [])]
            dups = sorted({i for i in ids if ids.count(i) > 1})
            self._add(
                name=f"drafting_history:snapshot_id_unique/{lang.upper()}",
                status="PASS" if not dups else "FAIL",
                detail=f"duplicates={dups[:5]}",
            )

    # ----- cross-references ----------------------------------------------

    def check_cross_references(self) -> None:
        en_a = {str(a["number"]) for a in self.articles_en}
        nl_a = {str(a["number"]) for a in self.articles_nl}
        en_r = {str(r["number"]) for r in self.recitals_en}
        nl_r = {str(r["number"]) for r in self.recitals_nl}

        unresolved: List[str] = []

        # article_to_recitals
        a2r = self.cross_refs.get("article_to_recitals", {})
        for art, recs in a2r.items():
            if str(art) not in en_a:
                unresolved.append(f"a2r src {art} missing in articles_en")
            if str(art) not in nl_a:
                unresolved.append(f"a2r src {art} missing in articles_nl")
            for rec in recs:
                rs = str(rec)
                if rs not in en_r:
                    unresolved.append(f"a2r tgt-rec {rs} missing in recitals_en (src={art})")
                if rs not in nl_r:
                    unresolved.append(f"a2r tgt-rec {rs} missing in recitals_nl (src={art})")

        # recital_to_articles
        r2a = self.cross_refs.get("recital_to_articles", {})
        for rec, arts in r2a.items():
            if str(rec) not in en_r:
                unresolved.append(f"r2a src {rec} missing in recitals_en")
            if str(rec) not in nl_r:
                unresolved.append(f"r2a src {rec} missing in recitals_nl")
            for art in arts:
                a = str(art)
                if a not in en_a:
                    unresolved.append(f"r2a tgt-art {a} missing in articles_en (src={rec})")
                if a not in nl_a:
                    unresolved.append(f"r2a tgt-art {a} missing in articles_nl (src={rec})")

        self._add(
            name="cross_references:targets_resolve",
            status="PASS" if not unresolved else "FAIL",
            detail=f"unresolved={len(unresolved)}; sample={unresolved[:3]}",
        )

        # Optional 4.9a/4.9b keys — soft-flag if absent.
        for key in (
            "article_to_articles_internal",
            "articles_referencing",
            "article_to_external_refs",
        ):
            if key not in self.cross_refs:
                self._add(
                    name=f"cross_references:{key}_present",
                    status="SOFT",
                    detail=f"{key} not yet ingested — tracked under 4.9a/4.9b (per catalogue)",
                )

        # Reverse symmetry of internal refs (when present).
        # Forward entries are dicts with target_article + extra context (paragraph,
        # location_in_source, subparagraph, target_kind). Reverse entries are
        # narrower dicts with source_article + a subset of context fields (per
        # step-4.9-completion-notes.md §6). The previous comparison stringified
        # entire forward dicts and matched them against source-article strings,
        # which never matched once the keys shipped. The relational definition is:
        # a forward edge (src → fwd.target_article) is symmetric iff
        # articles_referencing[fwd.target_article] contains an entry whose
        # source_article equals src.
        if "article_to_articles_internal" in self.cross_refs and "articles_referencing" in self.cross_refs:
            a2a = self.cross_refs["article_to_articles_internal"]
            ref_by = self.cross_refs["articles_referencing"]
            asymm = []
            for src, fwds in a2a.items():
                for fwd in fwds:
                    if not isinstance(fwd, dict):
                        continue
                    tgt = str(fwd.get("target_article", ""))
                    if not tgt:
                        continue
                    # Internal refs only; annex targets aren't expected to back-link.
                    if fwd.get("target_kind") not in (None, "article"):
                        continue
                    rev_list = ref_by.get(tgt, [])
                    rev_sources = {
                        str(r.get("source_article", ""))
                        for r in rev_list
                        if isinstance(r, dict)
                    }
                    if str(src) not in rev_sources:
                        asymm.append((src, tgt))
            self._add(
                name="cross_references:internal_reverse_symmetry",
                status="PASS" if not asymm else "FAIL",
                detail=f"asymmetric={len(asymm)}; sample={asymm[:3]}",
            )

        # External CELEX format (when present)
        if "article_to_external_refs" in self.cross_refs:
            ext = self.cross_refs["article_to_external_refs"]
            bad_celex = []
            gdpr_keyed_to_other = []
            for art, refs in ext.items():
                for r in refs:
                    celex = r.get("celex") if isinstance(r, dict) else None
                    if celex and not CELEX_RE.match(celex):
                        bad_celex.append((art, celex))
                    if isinstance(r, dict) and r.get("kind") == "external_gdpr" \
                            and celex != GDPR_CELEX:
                        gdpr_keyed_to_other.append((art, celex))
            self._add(
                name="cross_references:external_celex_format",
                status="PASS" if not bad_celex else "FAIL",
                detail=f"malformed={len(bad_celex)}; sample={bad_celex[:3]}",
            )
            self._add(
                name="cross_references:external_gdpr_celex",
                status="PASS" if not gdpr_keyed_to_other else "FAIL",
                detail=f"gdpr-tagged but wrong CELEX: {gdpr_keyed_to_other[:3]}",
            )

    # ----- omnibus -------------------------------------------------------

    def check_omnibus(self) -> None:
        self._add(
            name="omnibus:en_present",
            status="PASS" if self.omnibus_en else "FAIL",
            detail=f"len={len(self.omnibus_en)}",
        )
        # NL must NOT exist (or must be empty/null)
        if not self.omnibus_nl_present:
            self._add(
                name="omnibus:nl_absent",
                status="PASS",
                detail="omnibus_amendments_nl.json correctly absent (EN-only by design)",
            )
        else:
            try:
                with (self.data_dir / "omnibus_amendments_nl.json").open("r", encoding="utf-8") as f:
                    nl_blob = json.load(f)
                empty = (nl_blob is None
                         or (isinstance(nl_blob, list) and len(nl_blob) == 0)
                         or (isinstance(nl_blob, dict) and not nl_blob))
                self._add(
                    name="omnibus:nl_absent",
                    status="PASS" if empty else "FAIL",
                    detail=f"file present and non-empty: {type(nl_blob).__name__}",
                )
            except Exception as exc:
                self._add(
                    name="omnibus:nl_absent",
                    status="FAIL",
                    detail=f"file present but unreadable: {exc}",
                )

    # ----- guidance ------------------------------------------------------

    def check_guidance(self) -> None:
        if self.guidance is None:
            self._add(
                name="guidance:present",
                status="SOFT",
                detail="guidance.json not yet built — tracked under 5.5b (per catalogue)",
            )
            return
        # Each entry must declare its language(s). Original 5.5a corpus assumed a
        # single-language `language` field; 5.5a's bilingual extension (per
        # checklist-state.json scopeNote) introduced a `languages` array (e.g.
        # ["en", "nl"]) on bilingual entries. Accept either form.
        bad = []
        entries = self.guidance if isinstance(self.guidance, list) else self.guidance.get("entries", [])
        for e in entries:
            if not isinstance(e, dict):
                bad.append((None, "not_a_dict"))
                continue
            lang = e.get("language")
            langs = e.get("languages")
            valid_singular = lang in ("en", "nl")
            valid_plural = (
                isinstance(langs, list)
                and len(langs) > 0
                and all(l in ("en", "nl") for l in langs)
            )
            if not (valid_singular or valid_plural):
                bad.append((e.get("canonical_id"), lang if lang is not None else langs))
        self._add(
            name="guidance:language_field_populated",
            status="PASS" if not bad else "FAIL",
            detail=f"entries={len(entries)} bad={bad[:3]}",
        )

    # ----- annex titles + paragraphs (soft-flags) ------------------------

    def check_soft_flags(self) -> None:
        # Annex EN bare titles (catalogued)
        bare = [a["id"] for a in self.annexes_en
                if isinstance(a.get("title"), str)
                and re.fullmatch(r"ANNEX\s+[IVXLC]+", a["title"].strip())]
        if bare:
            self._add(
                name="soft:annex_en_bare_titles",
                status="SOFT",
                detail=f"EN annexes with bare titles: {sorted(bare)} (catalogued — future EN data refresh)",
            )

        # NL paragraph collapse (catalogued)
        collapsed = []
        for a in self.articles_nl:
            paras = a.get("paragraphs", [])
            if (len(paras) == 1 and paras[0].get("id") is None
                    and paras[0].get("number") is None):
                collapsed.append(str(a["number"]))
        if collapsed:
            self._add(
                name="soft:nl_paragraph_collapse",
                status="SOFT",
                detail=f"{len(collapsed)} NL articles with single collapsed paragraph (catalogued — intermediate-format divergence)",
            )

        # Paragraph-count divergence (informational)
        en_by = {str(a["number"]): a for a in self.articles_en}
        nl_by = {str(a["number"]): a for a in self.articles_nl}
        diffs = []
        for n in sorted(set(en_by) & set(nl_by), key=lambda x: int(x) if x.isdigit() else 9999):
            ec = len(en_by[n].get("paragraphs", []))
            lc = len(nl_by[n].get("paragraphs", []))
            if ec != lc:
                diffs.append((n, ec, lc))
        self._add(
            name="soft:paragraph_count_divergence",
            status="SOFT",
            detail=f"{len(diffs)} articles with EN/NL paragraph-count divergence (largest: {sorted(diffs, key=lambda d: -abs(d[1]-d[2]))[:3]})",
        )

    # ----- optional dist/ check ------------------------------------------

    def check_dist(self) -> None:
        if self.dist_dir is None or not self.dist_dir.exists():
            self._add(
                name="dist:skipped",
                status="SKIP",
                detail="dist/ not present — run `npm run build` to enable route-count parity checks",
            )
            return

        en_root = self.dist_dir / "en"
        nl_root = self.dist_dir / "nl"
        # Quick "post-4.3b shape" heuristic: dist/en/articles/ should exist.
        if not (en_root / "articles").exists() or not (nl_root / "articles").exists():
            self._add(
                name="dist:skipped",
                status="SKIP",
                detail=("dist/ present but pre-4.3b shape (no /en/articles/) — "
                        "rebuild required after 4.3b/4.4 to enable route-count checks"),
            )
            return

        for tree, expected in (("articles", EXPECTED_ARTICLES),
                                ("recitals", EXPECTED_RECITALS),
                                ("annexes", EXPECTED_ANNEXES)):
            en_count = self._count_route_pages(en_root / tree)
            nl_count = self._count_route_pages(nl_root / tree)
            ok = en_count == nl_count == expected
            self._add(
                name=f"dist:route_parity:{tree}",
                status="PASS" if ok else "FAIL",
                detail=f"EN={en_count} NL={nl_count} expected={expected}",
            )

    @staticmethod
    def _count_route_pages(root: Path) -> int:
        if not root.exists():
            return 0
        # Count leaf index.html files, excluding the listing index itself.
        # Each article/recital/annex page is /articles/.../article-N/index.html
        count = 0
        for p in root.rglob("index.html"):
            # Skip the top-level listing (root/index.html)
            if p.parent == root:
                continue
            # Skip chapter listing pages (root/chapter-N/index.html)
            rel = p.relative_to(root).parts
            if len(rel) == 2 and rel[0].startswith("chapter-"):
                continue
            count += 1
        return count

    # ----- run ------------------------------------------------------------

    def run(self) -> int:
        t0 = time.time()
        self.load_all()
        if self.fatal_load_error:
            return 2
        self.check_count_parity()
        self.check_id_set_parity()
        self.check_field_parity_articles()
        self.check_drafting_history()
        self.check_cross_references()
        self.check_omnibus()
        self.check_guidance()
        self.check_soft_flags()
        self.check_dist()
        self._runtime_s = time.time() - t0
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render_stdout(verifier: Verifier) -> None:
    width = max((len(r.name) for r in verifier.results), default=0)
    for r in verifier.results:
        print(f"  [{r.status:4}] {r.name:<{width}}  {r.detail}")
    fails = [r for r in verifier.results if r.is_unexpected_fail]
    softs = [r for r in verifier.results if r.status == "SOFT"]
    skips = [r for r in verifier.results if r.status == "SKIP"]
    passes = [r for r in verifier.results if r.status == "PASS"]
    print()
    print(f"  PASS: {len(passes)}    FAIL: {len(fails)}    "
          f"SOFT: {len(softs)}    SKIP: {len(skips)}    "
          f"runtime: {getattr(verifier, '_runtime_s', 0):.3f}s")


def render_report(verifier: Verifier, path: Path) -> None:
    fails = [r for r in verifier.results if r.is_unexpected_fail]
    softs = [r for r in verifier.results if r.status == "SOFT"]
    skips = [r for r in verifier.results if r.status == "SKIP"]
    passes = [r for r in verifier.results if r.status == "PASS"]
    today = time.strftime("%Y-%m-%d")
    lines: List[str] = []
    lines.append("# Parity Report")
    lines.append("")
    lines.append(f"**Generated:** {today}")
    lines.append(f"**Verifier:** scripts/verify_parity.py")
    if verifier.catalogue_path:
        lines.append(f"**Catalogue:** {verifier.catalogue_path.name}")
    lines.append(f"**Runtime:** {getattr(verifier, '_runtime_s', 0):.3f}s")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total checks: {len(verifier.results)}")
    lines.append(f"- PASS: {len(passes)}")
    lines.append(f"- FAIL (unexpected): {len(fails)}")
    lines.append(f"- SOFT (catalogued / informational): {len(softs)}")
    lines.append(f"- SKIP (optional, not run): {len(skips)}")
    lines.append("")
    lines.append("## Detailed results")
    lines.append("")
    for r in verifier.results:
        lines.append(f"### {r.name}")
        lines.append(f"- Status: **{r.status}**")
        if r.detail:
            lines.append(f"- Detail: {r.detail}")
        if r.expected is not None:
            lines.append(f"- Expected: `{r.expected}`")
        if r.actual is not None:
            lines.append(f"- Actual: `{r.actual}`")
        lines.append("")
    if fails:
        lines.append("## Unexpected failures")
        lines.append("")
        for r in fails:
            lines.append(f"- **{r.name}** — {r.detail}")
        lines.append("")
    else:
        lines.append("## Unexpected failures")
        lines.append("")
        lines.append("(none)")
        lines.append("")
    lines.append("## Idempotency")
    lines.append("")
    lines.append("Re-run `python scripts/verify_parity.py --report <same-path>` and "
                 "compare with the previous file. The verifier is read-only and "
                 "deterministic; the report should match byte-for-byte except for "
                 "the runtime line.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EN/NL parity verifier for the AI Act Annotated Edition.")
    parser.add_argument("--data-dir", default=str(DATA_DIR),
                        help=f"Path to src/data/ (default: {DATA_DIR})")
    parser.add_argument("--dist-dir", default=str(DIST_DIR),
                        help=f"Path to dist/ (default: {DIST_DIR}; route-parity check skipped if missing)")
    parser.add_argument("--report", default=None,
                        help="Optional path to write a Markdown report.")
    parser.add_argument("--catalogue", default=None,
                        help="Path to parity-asymmetry-catalogue-YYYY-MM-DD.md (recorded in the report).")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    dist_dir = Path(args.dist_dir) if args.dist_dir else None
    catalogue = Path(args.catalogue) if args.catalogue else (
        CONTROL_ROOM / "reference" / "parity-asymmetry-catalogue-2026-04-28.md"
        if CONTROL_ROOM is not None else None
    )

    verifier = Verifier(
        data_dir=data_dir,
        dist_dir=dist_dir,
        catalogue_path=catalogue if (catalogue and catalogue.exists()) else None,
    )
    exit_code = verifier.run()
    render_stdout(verifier)
    if args.report:
        render_report(verifier, Path(args.report))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
