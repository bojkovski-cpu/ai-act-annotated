#!/usr/bin/env python3
"""
verify_guidance_cross_links.py — Bi-directional integrity verifier for
guidance ↔ article cross-links.

Step 5.4, v1.1.

Reads the guidance index (`guidance_index_by_article.json`), the guidance
registry (`guidance.json`), and the rendered `dist/` output, and asserts:

  1. Data integrity: every reverse-index entry references a known
     guidance_id, a valid article number (1..113), a valid language, a
     populated pin_cite, and a populated location_in_doc.
  2. Forward direction (article → guidance): for each (guidance_id, article,
     lang) tuple in the index, the rendered article page at
     /dist/{lang}/articles/chapter-{C}/article-{N}/index.html contains a
     guidance card linking back to /{lang}/guidance/<canonical_id>/.
  3. Reverse direction (guidance → article): for each guidance doc, the
     rendered detail page at /dist/{lang}/guidance/<canonical_id>/index.html
     contains a "Cited articles" sidebar entry for every article cited in
     that language.
  4. Symmetric back-check: every gd-cited-link in the rendered HTML is
     backed by at least one row in the data file (no spurious anchors).

Outputs:
  - stdout: PASS/FAIL/SKIP line per check, summary footer.
  - exit code:
        0  all checks PASS (or only informational asymmetry rows)
        1  at least one mismatch
        2  required data file missing or malformed

Usage:
    python scripts/verify_guidance_cross_links.py
    python scripts/verify_guidance_cross_links.py --report \
        control-room/reference/guidance-cross-link-report-2026-04-30.md
    python scripts/verify_guidance_cross_links.py --dist-dir /tmp/54-build/aiact/dist

The verifier is read-only with respect to the data layer. It writes only
the optional Markdown report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "src" / "data"
DIST_DIR = REPO_ROOT / "dist"

ARTICLE_RANGE = range(1, 114)  # 1..113 inclusive
LANGS: Tuple[str, ...] = ("en", "nl")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP" | "INFO"
    detail: str = ""

    @property
    def is_fail(self) -> bool:
        return self.status == "FAIL"


@dataclass
class Verifier:
    data_dir: Path
    dist_dir: Optional[Path]
    results: List[CheckResult] = field(default_factory=list)
    fatal_load_error: bool = False

    guidance: List[Dict[str, Any]] = field(default_factory=list)
    index: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    articles_chapter: Dict[int, Any] = field(default_factory=dict)

    _runtime_s: float = 0.0

    # ---- helpers --------------------------------------------------------

    def _add(self, name: str, status: str, detail: str = "") -> None:
        self.results.append(CheckResult(name=name, status=status, detail=detail))

    def _load_json(self, name: str, required: bool = True) -> Any:
        path = self.data_dir / name
        if not path.exists():
            if required:
                self._add(f"load:{name}", "FAIL", f"Required file missing: {path}")
                self.fatal_load_error = True
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self._add(f"load:{name}", "FAIL", f"Malformed JSON: {exc}")
            self.fatal_load_error = True
            return None

    def _load_articles_chapter_map(self) -> None:
        # The chapter is needed to construct dist article-page paths.
        articles = self._load_json("articles_en.json", required=True) or []
        if not isinstance(articles, list):
            return
        for a in articles:
            try:
                num = int(a.get("number"))
            except (TypeError, ValueError):
                continue
            self.articles_chapter[num] = a.get("chapter")

    def load_all(self) -> None:
        self.guidance = self._load_json("guidance.json", required=True) or []
        self.index = self._load_json("guidance_index_by_article.json", required=True) or {}
        self._load_articles_chapter_map()

    # ---- Step 1: data integrity ----------------------------------------

    def check_data_integrity(self) -> None:
        guidance_ids: Set[str] = {
            g.get("canonical_id") for g in self.guidance if isinstance(g, dict)
        }

        bad_id: List[Tuple[Any, Any]] = []
        bad_art: List[Tuple[Any, str]] = []
        bad_lang: List[Tuple[Any, Any, Any]] = []
        bad_pin: List[Tuple[Any, Any, Any]] = []
        bad_loc: List[Tuple[Any, Any, Any]] = []
        total = 0

        for art_str, entries in self.index.items():
            try:
                art_num = int(art_str)
            except ValueError:
                bad_art.append((art_str, "not_an_integer"))
                continue
            if art_num not in ARTICLE_RANGE:
                bad_art.append((art_str, "out_of_range"))

            if not isinstance(entries, list):
                bad_id.append((art_str, "entries_not_a_list"))
                continue

            for e in entries:
                total += 1
                if not isinstance(e, dict):
                    bad_id.append((art_str, "not_a_dict"))
                    continue
                gid = e.get("guidance_id")
                if gid not in guidance_ids:
                    bad_id.append((art_str, gid))
                lang = e.get("language")
                if lang not in LANGS:
                    bad_lang.append((art_str, gid, lang))
                pin = e.get("pin_cite")
                if not isinstance(pin, dict) or not pin.get("raw"):
                    bad_pin.append((art_str, gid, pin))
                loc = e.get("location_in_doc")
                if not isinstance(loc, dict):
                    bad_loc.append((art_str, gid, loc))

        self._add("data:total_entries", "INFO", f"total={total}")
        self._add("data:guidance_ids_known",
                  "PASS" if not bad_id else "FAIL",
                  f"unknown={len(bad_id)}; sample={bad_id[:3]}")
        self._add("data:article_numbers_valid",
                  "PASS" if not bad_art else "FAIL",
                  f"invalid={len(bad_art)}; sample={bad_art[:3]}")
        self._add("data:language_field_valid",
                  "PASS" if not bad_lang else "FAIL",
                  f"invalid={len(bad_lang)}; sample={bad_lang[:3]}")
        self._add("data:pin_cite_present",
                  "PASS" if not bad_pin else "FAIL",
                  f"missing/empty={len(bad_pin)}; sample={bad_pin[:3]}")
        self._add("data:location_in_doc_present",
                  "PASS" if not bad_loc else "FAIL",
                  f"missing={len(bad_loc)}; sample={bad_loc[:3]}")

    # ---- Steps 2 & 3: rendered-HTML cross-link checks ------------------

    def _article_page_path(self, lang: str, article_num: int) -> Optional[Path]:
        chapter = self.articles_chapter.get(article_num)
        if chapter is None or self.dist_dir is None:
            return None
        return (self.dist_dir / lang / "articles"
                / f"chapter-{chapter}" / f"article-{article_num}" / "index.html")

    def _guidance_page_path(self, lang: str, canonical_id: str) -> Optional[Path]:
        if self.dist_dir is None:
            return None
        return self.dist_dir / lang / "guidance" / canonical_id / "index.html"

    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return None

    def check_dist_present(self) -> bool:
        if self.dist_dir is None or not self.dist_dir.exists():
            self._add("dist:present", "SKIP",
                      "dist/ missing — run `npm run build` before invoking the verifier")
            return False
        has_any = any((self.dist_dir / l / "guidance").exists() for l in LANGS)
        if not has_any:
            self._add("dist:present", "SKIP", "dist/ exists but no /{lang}/guidance/ tree found")
            return False
        self._add("dist:present", "PASS", f"dist/ at {self.dist_dir}")
        return True

    def check_forward_links(self) -> None:
        """Article page Guidance tab contains a card for every cited (guidance_id, lang)."""
        missing: List[Tuple[str, int, str]] = []  # (gid, article, lang)
        checked = 0
        for art_str, entries in self.index.items():
            try:
                art_num = int(art_str)
            except ValueError:
                continue
            # Multiple pin-cites on the same article render as ONE card per
            # (gid, lang); group accordingly so we test each card once.
            tuples: Set[Tuple[str, str]] = set()
            for e in entries:
                if isinstance(e, dict):
                    gid = e.get("guidance_id")
                    lang = e.get("language")
                    if gid and lang in LANGS:
                        tuples.add((gid, lang))

            for gid, lang in tuples:
                checked += 1
                page = self._article_page_path(lang, art_num)
                if page is None:
                    missing.append((gid, art_num, lang))
                    continue
                html = self._read_text(page)
                if html is None:
                    missing.append((gid, art_num, lang))
                    continue
                panel_marker = 'data-panel="guidance"'
                href_marker = f'/{lang}/guidance/{gid}/'
                if panel_marker not in html or href_marker not in html:
                    missing.append((gid, art_num, lang))
        self._add(
            "dist:forward_links",
            "PASS" if not missing else "FAIL",
            f"checked={checked}; missing={len(missing)}; sample={missing[:5]}",
        )

    def check_reverse_links(self) -> None:
        """Guidance detail "Cited articles" sidebar contains every cited article."""
        expected: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
        for art_str, entries in self.index.items():
            try:
                art_num = int(art_str)
            except ValueError:
                continue
            for e in entries:
                if isinstance(e, dict):
                    gid = e.get("guidance_id")
                    lang = e.get("language")
                    if gid and lang in LANGS:
                        expected[(gid, lang)].add(art_num)

        missing: List[Tuple[str, str, int]] = []
        checked = 0
        for (gid, lang), arts in expected.items():
            page = self._guidance_page_path(lang, gid)
            if page is None:
                missing.extend((gid, lang, n) for n in sorted(arts))
                continue
            html = self._read_text(page)
            if html is None:
                missing.extend((gid, lang, n) for n in sorted(arts))
                continue
            for n in arts:
                checked += 1
                # The cited-articles sidebar emits anchors of shape
                # <a class="gd-cited-link" href="/{lang}/articles/chapter-{C}/article-{N}/">
                # The 5.4 deep-link work appended an optional fragment
                # (#guidance) so the article page opens with the Guidance tab
                # pre-selected; the fragment is allowed but not required.
                if not re.search(
                    rf'href="/{lang}/articles/chapter-\d+/article-{n}/(?:#[a-z-]+)?"',
                    html,
                ):
                    missing.append((gid, lang, n))
        self._add(
            "dist:reverse_links",
            "PASS" if not missing else "FAIL",
            f"checked={checked}; missing={len(missing)}; sample={missing[:5]}",
        )

    def check_symmetric_back(self) -> None:
        """Every gd-cited-link in dist HTML is backed by a row in the index."""
        if self.dist_dir is None:
            return
        # Match either attribute order: class then href, or href then class.
        # Allow an optional #fragment (5.4 deep-link work appends #guidance).
        cited_link_re = re.compile(
            r'(?:class="gd-cited-link"\s+href="/(en|nl)/articles/chapter-\d+/article-(\d+)/(?:#[a-z-]+)?"|'
            r'href="/(en|nl)/articles/chapter-\d+/article-(\d+)/(?:#[a-z-]+)?"\s+class="gd-cited-link")'
        )

        expected: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
        for art_str, entries in self.index.items():
            try:
                art_num = int(art_str)
            except ValueError:
                continue
            for e in entries:
                if isinstance(e, dict):
                    gid = e.get("guidance_id")
                    lang = e.get("language")
                    if gid and lang in LANGS:
                        expected[(gid, lang)].add(art_num)

        spurious: List[Tuple[str, str, int]] = []
        for g in self.guidance:
            gid = g.get("canonical_id")
            for lang in LANGS:
                page = self._guidance_page_path(lang, gid)
                html = self._read_text(page) if page else None
                if html is None:
                    continue
                claimed: Set[int] = set()
                for m in cited_link_re.finditer(html):
                    found_lang = m.group(1) or m.group(3)
                    found_num = m.group(2) or m.group(4)
                    if found_lang == lang and found_num:
                        claimed.add(int(found_num))
                exp = expected.get((gid, lang), set())
                for n in sorted(claimed - exp):
                    spurious.append((gid, lang, n))
        self._add(
            "dist:reverse_back-check",
            "PASS" if not spurious else "FAIL",
            f"spurious={len(spurious)}; sample={spurious[:5]}",
        )

    # ---- Step 4: asymmetric coverage (informational) -------------------

    def report_asymmetric_coverage(self) -> None:
        en_pairs: Set[Tuple[int, str]] = set()
        nl_pairs: Set[Tuple[int, str]] = set()
        # Pin-cite rows split by article+gid+pin (so 2-EN-vs-1-NL on the
        # same article surfaces as a per-pin asymmetry, not just article-level).
        en_pin_rows: List[Tuple[int, str, str]] = []  # (art, gid, raw)
        nl_pin_rows: List[Tuple[int, str, str]] = []

        for art_str, entries in self.index.items():
            try:
                art_num = int(art_str)
            except ValueError:
                continue
            for e in entries:
                if not isinstance(e, dict):
                    continue
                gid = e.get("guidance_id") or ""
                lang = e.get("language")
                pin = e.get("pin_cite") or {}
                # Use a normalised pin signature (location section/page/footnote)
                # so EN "Article 5" and NL "Artikel 5" at the same location
                # match each other and don't show up as asymmetric.
                loc = e.get("location_in_doc") or {}
                sig = (loc.get("section"), loc.get("page"), loc.get("footnote"),
                       pin.get("paragraph"), pin.get("letter"))
                sig_str = repr(sig)
                if lang == "en":
                    en_pairs.add((art_num, gid))
                    en_pin_rows.append((art_num, gid, sig_str))
                elif lang == "nl":
                    nl_pairs.add((art_num, gid))
                    nl_pin_rows.append((art_num, gid, sig_str))

        en_only_articles = sorted(en_pairs - nl_pairs)
        nl_only_articles = sorted(nl_pairs - en_pairs)
        en_only_pins = sorted(set(en_pin_rows) - set(nl_pin_rows))
        nl_only_pins = sorted(set(nl_pin_rows) - set(en_pin_rows))

        self._add(
            "asymmetry:en_only_articles",
            "INFO",
            f"count={len(en_only_articles)}; sample={en_only_articles[:5]}",
        )
        self._add(
            "asymmetry:nl_only_articles",
            "INFO",
            f"count={len(nl_only_articles)}; sample={nl_only_articles[:5]}",
        )
        self._add(
            "asymmetry:en_only_pins",
            "INFO",
            f"count={len(en_only_pins)}; sample={en_only_pins[:5]}",
        )
        self._add(
            "asymmetry:nl_only_pins",
            "INFO",
            f"count={len(nl_only_pins)}; sample={nl_only_pins[:5]}",
        )

    # ---- orchestration --------------------------------------------------

    def run(self) -> int:
        t0 = time.time()
        self.load_all()
        if self.fatal_load_error:
            self._runtime_s = time.time() - t0
            return 2
        self.check_data_integrity()
        if self.check_dist_present():
            self.check_forward_links()
            self.check_reverse_links()
            self.check_symmetric_back()
        self.report_asymmetric_coverage()
        self._runtime_s = time.time() - t0
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render_stdout(v: Verifier) -> None:
    width = max((len(r.name) for r in v.results), default=0)
    for r in v.results:
        print(f"  [{r.status:4}] {r.name:<{width}}  {r.detail}")
    fails = [r for r in v.results if r.is_fail]
    skips = [r for r in v.results if r.status == "SKIP"]
    passes = [r for r in v.results if r.status == "PASS"]
    infos = [r for r in v.results if r.status == "INFO"]
    print()
    print(f"  PASS: {len(passes)}    FAIL: {len(fails)}    "
          f"SKIP: {len(skips)}    INFO: {len(infos)}    "
          f"runtime: {v._runtime_s:.3f}s")


def render_report(v: Verifier, path: Path) -> None:
    today = time.strftime("%Y-%m-%d")
    fails = [r for r in v.results if r.is_fail]
    skips = [r for r in v.results if r.status == "SKIP"]
    passes = [r for r in v.results if r.status == "PASS"]
    infos = [r for r in v.results if r.status == "INFO"]
    lines = [
        "# Guidance Cross-Link Report",
        "",
        f"**Generated:** {today}",
        f"**Verifier:** scripts/verify_guidance_cross_links.py",
        f"**Runtime:** {v._runtime_s:.3f}s",
        "",
        "## Summary",
        "",
        f"- Total checks: {len(v.results)}",
        f"- PASS: {len(passes)}",
        f"- FAIL: {len(fails)}",
        f"- SKIP: {len(skips)}",
        f"- INFO: {len(infos)}",
        "",
        "## Detailed results",
        "",
    ]
    for r in v.results:
        lines.append(f"### {r.name}")
        lines.append(f"- Status: **{r.status}**")
        if r.detail:
            lines.append(f"- Detail: {r.detail}")
        lines.append("")
    if fails:
        lines.append("## Unexpected failures")
        lines.append("")
        for r in fails:
            lines.append(f"- **{r.name}** — {r.detail}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bi-directional guidance↔article cross-link verifier (Step 5.4).",
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR),
                        help=f"Path to src/data/ (default: {DATA_DIR})")
    parser.add_argument("--dist-dir", default=str(DIST_DIR),
                        help=f"Path to dist/ (default: {DIST_DIR}; rendered checks SKIP if missing)")
    parser.add_argument("--report", default=None,
                        help="Optional path to write a Markdown report.")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    dist_dir = Path(args.dist_dir) if args.dist_dir else None

    v = Verifier(data_dir=data_dir, dist_dir=dist_dir)
    exit_code = v.run()
    render_stdout(v)
    if args.report:
        render_report(v, Path(args.report))
    if exit_code == 0 and any(r.is_fail for r in v.results):
        return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
