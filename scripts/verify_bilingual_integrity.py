#!/usr/bin/env python3
"""
verify_bilingual_integrity.py - Step 4.8, v1.1.

Bilingual link-integrity validator for the AI Act Annotated Edition built tree.

Checks:
  1. Internal 404s              (categorised: catalogued / unexpected / etc.)
  2. Hreflang round-trips       (with catalogue awareness)
  3. Decision 3 disclosure       (article-level)
  4. Internal-reference (4.9b)   (skipped if cross-refs not yet ingested)
  5. External URL format         (GDPR + EUR-Lex regex)
  6. Sitemap accuracy
  7. Robots.txt
  8. Zero-byte HTML              (build-render swallowed errors)
  9. Sidebar legacy link

Outputs a markdown report at control-room/reference/link-integrity-report-YYYY-MM-DD.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST = REPO_ROOT / "dist"
SRC_DATA = REPO_ROOT / "src" / "data"
CONTROL_ROOM = REPO_ROOT.parent / "control-room"
REF_DIR = CONTROL_ROOM / "reference"
PROD_HOST = "aiact.annotated.nl"
PROD_ORIGIN = "https://" + PROD_HOST


@dataclass
class CheckResult:
    name: str
    status: str
    findings: str
    details: List[str] = field(default_factory=list)


CHECKS: List[CheckResult] = []


def emit(name: str, status: str, findings: str, details: Optional[List[str]] = None) -> None:
    cr = CheckResult(name=name, status=status, findings=findings, details=details or [])
    CHECKS.append(cr)
    short = findings if len(findings) < 130 else findings[:127] + "..."
    print("  " + status.ljust(4) + "  " + name.ljust(50) + " " + short)


def load_catalogued_dh_asymmetries() -> Dict[str, Set[Tuple[str, str, str]]]:
    en = json.loads((SRC_DATA / "drafting_history_en.json").read_text("utf-8"))
    nl = json.loads((SRC_DATA / "drafting_history_nl.json").read_text("utf-8"))
    def keys(snaps):
        return {(s["stage"], s["content_type"], str(s["number"])) for s in snaps}
    en_keys = keys(en["snapshots"])
    nl_keys = keys(nl["snapshots"])
    return {"en_missing": nl_keys - en_keys, "nl_missing": en_keys - nl_keys}


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[str] = []
        self.alternates: Dict[str, str] = {}
        self.canonical: Optional[str] = None
        self.meta_refresh: Optional[str] = None
        self.dh_gap_links: List[str] = []
        self._in_gap_notice: int = 0

    def handle_starttag(self, tag, attrs_list):
        attrs = dict(attrs_list)
        if tag == "a":
            href = attrs.get("href")
            if href:
                self.anchors.append(href)
                if self._in_gap_notice > 0:
                    self.dh_gap_links.append(href)
        elif tag == "link":
            rel = attrs.get("rel", "")
            href = attrs.get("href")
            if "alternate" in rel and "hreflang" in attrs:
                self.alternates[attrs["hreflang"]] = href or ""
            if "canonical" in rel and href:
                self.canonical = href
        elif tag == "meta":
            if attrs.get("http-equiv", "").lower() == "refresh":
                content = attrs.get("content", "")
                m = re.search(r"url=([^;]+)", content, re.IGNORECASE)
                if m:
                    self.meta_refresh = m.group(1).strip()
        cls = attrs.get("class", "")
        if cls and "dh-gap-notice" in cls:
            self._in_gap_notice += 1

    def handle_endtag(self, tag):
        if tag == "div" and self._in_gap_notice > 0:
            self._in_gap_notice -= 1


def parse_html(path: Path) -> LinkExtractor:
    parser = LinkExtractor()
    try:
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print("  WARN  parse error in " + str(path.relative_to(DIST)) + ": " + str(e), file=sys.stderr)
    return parser


def url_to_dist_path(url: str, current_file: Path) -> Optional[Path]:
    url = url.split("#", 1)[0]
    if not url:
        return current_file
    url = url.split("?", 1)[0]
    if not url:
        return current_file
    if url.startswith(("http://", "https://", "//", "mailto:", "tel:", "javascript:")):
        return None
    if url.startswith("/"):
        target = DIST / url.lstrip("/")
    else:
        target = (current_file.parent / url).resolve()
    if target.is_dir():
        c = target / "index.html"
        return c if c.exists() else None
    if target.exists():
        return target
    if Path(str(target) + ".html").exists():
        return Path(str(target) + ".html")
    if (target / "index.html").exists():
        return target / "index.html"
    return None


def url_to_dist_path_from_origin(url: str) -> Optional[Path]:
    if not url.startswith(PROD_ORIGIN):
        return None
    rel = url[len(PROD_ORIGIN):].lstrip("/")
    target = DIST / rel
    if target.is_dir():
        c = target / "index.html"
        return c if c.exists() else None
    if target.exists():
        return target
    if (target / "index.html").exists():
        return target / "index.html"
    if rel == "":
        idx = DIST / "index.html"
        return idx if idx.exists() else None
    return None


def iter_html_files() -> List[Path]:
    return sorted(DIST.rglob("*.html"))


def is_redirect_stub(parser: LinkExtractor) -> bool:
    return parser.meta_refresh is not None


# Check 1 — internal 404s (regex-fast)

_HREF_RE = re.compile(r'<a\s[^>]*href="([^"]+)"', re.IGNORECASE)
_META_RE = re.compile(r'<meta\s[^>]*http-equiv="refresh"[^>]*content="[^"]*url=([^";]+)', re.IGNORECASE)


def classify_broken(href: str, src: str) -> str:
    h = href.split("#", 1)[0].split("?", 1)[0]
    if re.match(r"^/(en|nl)/history/commission-2021/(articles|recitals|annexes)/", h):
        return "catalogued_dh"
    if h == "/history/final-2024/" or h.startswith("/history/final-2024/"):
        return "final_2024_sidebar"
    if src.endswith("[meta-refresh]") and src.startswith("history/"):
        return "meta_refresh_stub_catalogued"
    return "unexpected"


def check_internal_404s() -> None:
    broken: List[Tuple[str, str]] = []
    total_internal = 0
    total_external = 0
    files = iter_html_files()
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(f.relative_to(DIST))
        for href in _HREF_RE.findall(txt):
            if href.startswith(("http://", "https://", "//", "mailto:", "tel:", "javascript:")):
                total_external += 1
                continue
            if href.startswith("#"):
                continue
            total_internal += 1
            if url_to_dist_path(href, f) is None:
                broken.append((href, rel))
        m = _META_RE.search(txt)
        if m:
            url = m.group(1).strip()
            if not url.startswith(("http://", "https://")):
                total_internal += 1
                if url_to_dist_path(url, f) is None:
                    broken.append((url, rel + " [meta-refresh]"))

    by_class: Dict[str, List[Tuple[str, str]]] = {}
    for href, src in broken:
        by_class.setdefault(classify_broken(href, src), []).append((href, src))

    n_total = len(broken)
    n_cat = len(by_class.get("catalogued_dh", []))
    n_stub = len(by_class.get("meta_refresh_stub_catalogued", []))
    n_final = len(by_class.get("final_2024_sidebar", []))
    n_unx = len(by_class.get("unexpected", []))

    findings = (
        str(total_internal) + " anchors / " + str(len(files)) + " files. "
        "Broken: " + str(n_total) + " (" + str(n_cat) + " catalogued, " +
        str(n_stub) + " legacy-stub meta-refresh, " + str(n_final) +
        " /history/final-2024/, " + str(n_unx) + " unexpected). " +
        str(total_external) + " external skipped."
    )

    if n_final == 0 and n_unx == 0:
        if n_cat == 0 and n_stub == 0:
            emit("Internal 404s", "PASS", findings)
        else:
            d = ["  Catalogued asymmetry sample:"]
            d += ["    " + h + "  <-  " + s for h, s in sorted(by_class.get("catalogued_dh", []))[:5]]
            if n_stub:
                d.append("  Legacy stub meta-refresh sample:")
                d += ["    " + h + "  <-  " + s for h, s in sorted(by_class.get("meta_refresh_stub_catalogued", []))[:5]]
            emit("Internal 404s", "SOFT", findings, details=d)
    else:
        d = []
        if n_final:
            d.append("  /history/final-2024/ broken (Sidebar.astro line 127 emits link; 4.4 dropped final-2024 stage). " + str(n_final) + " affected pages.")
            d.append("  Sample sources:")
            d += ["    " + s for h, s in sorted(by_class.get("final_2024_sidebar", []))[:5]]
        if n_unx:
            d.append("  Unexpected (sample):")
            d += ["    " + h + "  <-  " + s for h, s in sorted(by_class.get("unexpected", []))[:10]]
        if n_cat or n_stub:
            d.append("  Also: " + str(n_cat) + " catalogued + " + str(n_stub) + " legacy-stub meta-refresh — expected per i18n Decision 6 and 4.4 §7.")
        emit("Internal 404s", "FAIL", findings, details=d)


# Check 2 — hreflang round-trips

def is_catalogued_history_detail(rel_path: str, en_missing, nl_missing) -> Optional[str]:
    m = re.match(r"^(en|nl)/history/([^/]+)/(articles|recitals|annexes)/(article|recital|annex)-([^/]+)/index\.html$", rel_path)
    if not m:
        return None
    page_lang, stage, ctype, _kind, slug = m.groups()
    number = slug.upper() if ctype == "annexes" else slug
    key = (stage, ctype, number)
    if key in en_missing and page_lang == "nl":
        return "en_missing"
    if key in nl_missing and page_lang == "en":
        return "nl_missing"
    return None


def check_hreflang_roundtrips(catalogue) -> None:
    en_files = sorted((DIST / "en").rglob("index.html"))
    nl_files = sorted((DIST / "nl").rglob("index.html"))
    failures: List[str] = []
    pages_checked = 0
    pages_skipped_stub = 0
    pages_skipped_catalogue = 0
    pages_skipped_zero = 0

    for f in en_files + nl_files:
        if f.stat().st_size == 0:
            pages_skipped_zero += 1
            continue
        # Posix-flip for catalogue regex match — Windows separators would
        # otherwise let catalogued pages skip the catalogue test entirely.
        rel = str(f.relative_to(DIST)).replace("\\", "/")
        if is_catalogued_history_detail(rel, catalogue["en_missing"], catalogue["nl_missing"]):
            pages_skipped_catalogue += 1
            continue
        parser = parse_html(f)
        if is_redirect_stub(parser):
            pages_skipped_stub += 1
            continue
        pages_checked += 1
        for need in ("en", "nl", "x-default"):
            if need not in parser.alternates:
                failures.append(rel + ": missing hreflang=" + need)
        if not all(k in parser.alternates for k in ("en", "nl", "x-default")):
            continue
        en_alt = parser.alternates["en"]
        nl_alt = parser.alternates["nl"]
        xd_alt = parser.alternates["x-default"]
        if xd_alt != en_alt:
            failures.append(rel + ": x-default != en alt")
        if url_to_dist_path_from_origin(en_alt) is None:
            failures.append(rel + ": en alt does not resolve: " + en_alt)
        if url_to_dist_path_from_origin(nl_alt) is None:
            failures.append(rel + ": nl alt does not resolve: " + nl_alt)

    failures = sorted(set(failures))
    summary = (str(pages_checked) + " pages PASS; " +
               str(pages_skipped_catalogue) + " catalogued asymmetric pages skipped; " +
               str(pages_skipped_stub) + " redirect stubs skipped; " +
               str(pages_skipped_zero) + " zero-byte skipped (see separate check)")
    if not failures:
        emit("Hreflang round-trips", "PASS", summary)
    else:
        emit("Hreflang round-trips", "FAIL",
             str(len(failures)) + " hreflang failures (excluding catalogue + stubs)",
             details=["  " + x for x in failures[:30]])


# Check 3 — Decision 3 disclosures

def check_decision_3_disclosures(catalogue) -> None:
    arts_en = json.loads((SRC_DATA / "articles_en.json").read_text("utf-8"))
    chapter_for = {str(a["number"]): str(a["chapter"]) for a in arts_en}
    en_missing = catalogue["en_missing"]
    failures: List[str] = []
    passes: List[str] = []
    expected_articles = sum(1 for (s, c, n) in en_missing if c == "articles")
    for (stage, ctype, number) in sorted(en_missing):
        if ctype != "articles":
            continue
        chapter = chapter_for.get(number)
        if chapter is None:
            failures.append("article " + number + " (stage " + stage + "): chapter not found")
            continue
        page = DIST / "en" / "articles" / ("chapter-" + chapter) / ("article-" + number) / "index.html"
        if not page.exists():
            failures.append(str(page.relative_to(DIST)) + ": page missing")
            continue
        parser = parse_html(page)
        if not parser.dh_gap_links:
            failures.append(str(page.relative_to(DIST)) + ": no disclosure link")
            continue
        expected_path = "/nl/history/" + stage + "/articles/article-" + number + "/"
        if not any(expected_path in href for href in parser.dh_gap_links):
            failures.append(str(page.relative_to(DIST)) + ": disclosure link wrong (expected " + expected_path + ")")
            continue
        target = DIST / "nl" / "history" / stage / "articles" / ("article-" + number) / "index.html"
        if not target.exists():
            failures.append(str(page.relative_to(DIST)) + ": disclosure target missing on disk")
            continue
        passes.append(str(page.relative_to(DIST)))
    if not failures and len(passes) == expected_articles:
        emit("Decision 3 disclosure (articles)", "PASS",
             str(len(passes)) + "/" + str(expected_articles) + " EN-missing article pages render disclosure with valid NL link")
    else:
        emit("Decision 3 disclosure (articles)", "FAIL",
             str(len(failures)) + " failures across " + str(expected_articles) + " expected gaps",
             details=["  " + x for x in failures[:20]])

    expected_recitals = sum(1 for (s, c, n) in en_missing if c == "recitals")
    expected_annexes = sum(1 for (s, c, n) in en_missing if c == "annexes")
    soft = ("Recital/annex EN-missing gaps NOT rendered on content pages (" +
            str(expected_recitals) + " recitals + " + str(expected_annexes) + " annexes). "
            "Per 4.4 completion notes, DraftingHistory component is wired into ArticleBlock only; "
            "recital/annex page integration is a documented 4.4 carryover ('out of scope for this step but trivial'). "
            "NL stage detail pages exist and are reachable via the language switcher.")
    emit("Decision 3 disclosure (recitals/annexes)", "SOFT", soft)


# Check 4 — internal-reference wraps

def check_internal_reference_wraps() -> None:
    cr = json.loads((SRC_DATA / "cross_references.json").read_text("utf-8"))
    if "article_to_articles_internal" not in cr:
        emit("Internal-reference wrap (4.9b)", "SKIP",
             "article_to_articles_internal not present in cross_references.json (4.9a/4.9b not yet shipped)")
        return
    refs = cr["article_to_articles_internal"]
    sample = random.Random(20260428).sample(list(refs.keys()), min(10, len(refs)))
    arts_en = json.loads((SRC_DATA / "articles_en.json").read_text("utf-8"))
    chapter_for = {str(a["number"]): str(a["chapter"]) for a in arts_en}
    failures: List[str] = []
    for article_n in sample:
        expected = refs[article_n]
        if not expected:
            continue
        chapter = chapter_for.get(str(article_n))
        if chapter is None:
            failures.append("article " + str(article_n) + ": chapter not found")
            continue
        page = DIST / "en" / "articles" / ("chapter-" + chapter) / ("article-" + str(article_n)) / "index.html"
        if not page.exists():
            failures.append("article " + str(article_n) + ": page missing")
            continue
        parser = parse_html(page)
        # Annex refs wrap to /en/annexes/annex-{id}/, article refs wrap to
        # /en/articles/.../article-{N}/. Both shapes are valid; pick the
        # right anchor pool per target_kind so annex refs (Roman-numeral
        # target_article) don't generate false-positive misses against the
        # article-only pool. target_kind absent or 'article' → article wrap.
        rendered_articles = [h for h in parser.anchors if "/en/articles/" in h]
        rendered_annexes = [h for h in parser.anchors if "/en/annexes/" in h]
        for ref in expected:
            ref_target = ref.get("target_article") if isinstance(ref, dict) else ref
            ref_kind = ref.get("target_kind") if isinstance(ref, dict) else None
            if ref_kind == "annex":
                pat = "/annex-" + str(ref_target).lower() + "/"
                pool = rendered_annexes
                kind_label = "annex"
            else:
                pat = "/article-" + str(ref_target) + "/"
                pool = rendered_articles
                kind_label = "article"
            if not any(pat in r for r in pool):
                failures.append("article " + str(article_n) + ": expected ref to " + kind_label + " " + str(ref_target) + " not rendered")
    if failures:
        emit("Internal-reference wrap (4.9b sampled)", "FAIL",
             str(len(failures)) + " mismatches in " + str(len(sample)) + "-article sample",
             details=["  " + x for x in failures[:20]])
    else:
        emit("Internal-reference wrap (4.9b sampled)", "PASS",
             str(len(sample)) + " sampled articles render expected internal refs")


# Check 5 — external URL format

# Two valid shapes per step-4.9-completion-notes.md §11:
#   - /article/{N}/  → specific GDPR article cited
#   - /{lang}/       → instrument-only mention (no specific article)
# Reject anything else (e.g., /article/abc/, /article//).
GDPR_PATTERN = re.compile(
    r"^https://gdpr\.annotated\.nl/(en|nl)/(?:article/(\d+)/?|)(?:#.*)?$"
)
EUR_LEX_ELI = re.compile(r"^https://eur-lex\.europa\.eu/eli/(reg|dir|dec)/(\d{4})/(\d+)(/[\w/]*)?$")
EUR_LEX_CELEX = re.compile(r"^https://eur-lex\.europa\.eu/legal-content/(EN|NL)/TXT/?\?uri=CELEX:(3\d{4}[RLDC]\d{4})(?:[&?#].*)?$")


def check_external_url_format() -> None:
    gdpr_refs: List[Tuple[str, str]] = []
    eurlex_refs: List[Tuple[str, str]] = []
    for f in iter_html_files():
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in re.finditer(r'https://gdpr\.annotated\.nl/[^\s"\'<>]+', txt):
            gdpr_refs.append((m.group(0), str(f.relative_to(DIST))))
        for m in re.finditer(r'https://eur-lex\.europa\.eu/[^\s"\'<>]+', txt):
            eurlex_refs.append((m.group(0), str(f.relative_to(DIST))))

    rng = random.Random(20260428)
    g_sample = rng.sample(gdpr_refs, min(20, len(gdpr_refs))) if gdpr_refs else []
    e_sample = rng.sample(eurlex_refs, min(20, len(eurlex_refs))) if eurlex_refs else []

    g_bad = []
    for url, src in g_sample:
        m = GDPR_PATTERN.match(url)
        if not m:
            g_bad.append((url, src, "shape mismatch"))
            continue
        page_lang = "en" if src.startswith("en/") else ("nl" if src.startswith("nl/") else None)
        if page_lang and m.group(1) != page_lang:
            g_bad.append((url, src, "lang mismatch"))

    e_bad = []
    for url, src in e_sample:
        if EUR_LEX_ELI.match(url):
            continue
        if EUR_LEX_CELEX.match(url):
            m = EUR_LEX_CELEX.match(url)
            page_lang = "en" if src.startswith("en/") else ("nl" if src.startswith("nl/") else None)
            if page_lang and m.group(1).lower() != page_lang:
                e_bad.append((url, src, "CELEX lang mismatch"))
            continue
        e_bad.append((url, src, "shape mismatch (neither ELI nor CELEX form)"))

    if not gdpr_refs:
        emit("External URL format (GDPR)", "SOFT", "0 GDPR-host links rendered")
    elif g_bad:
        emit("External URL format (GDPR)", "FAIL",
             str(len(g_bad)) + "/" + str(len(g_sample)) + " sampled malformed",
             details=["  " + u + " (" + r + ") <- " + s for (u, s, r) in g_bad[:10]])
    else:
        emit("External URL format (GDPR)", "PASS",
             str(len(g_sample)) + "/" + str(len(gdpr_refs)) + " sampled — well-formed and lang-matched")

    if not eurlex_refs:
        emit("External URL format (EUR-Lex)", "SOFT", "0 EUR-Lex links rendered")
    elif e_bad:
        emit("External URL format (EUR-Lex)", "FAIL",
             str(len(e_bad)) + "/" + str(len(e_sample)) + " sampled malformed",
             details=["  " + u + " (" + r + ") <- " + s for (u, s, r) in e_bad[:10]])
    else:
        unique = len(set(u for u, _ in eurlex_refs))
        emit("External URL format (EUR-Lex)", "PASS",
             str(len(e_sample)) + "/" + str(len(eurlex_refs)) + " sampled — all well-formed (" +
             str(unique) + " unique)")


# Check 6 — sitemap

def check_sitemap() -> None:
    idx_path = DIST / "sitemap-index.xml"
    if not idx_path.exists():
        emit("Sitemap accuracy", "FAIL", "sitemap-index.xml missing")
        return
    NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    idx_root = ET.parse(idx_path).getroot()
    sub_locs = [loc.text for loc in idx_root.findall("sm:sitemap/sm:loc", NS)]
    all_urls: List[str] = []
    for sub in sub_locs:
        if not sub or not sub.startswith(PROD_ORIGIN):
            continue
        rel = sub[len(PROD_ORIGIN):].lstrip("/")
        sub_path = DIST / rel
        if not sub_path.exists():
            emit("Sitemap accuracy", "FAIL", "sub-sitemap missing: " + sub)
            return
        sub_root = ET.parse(sub_path).getroot()
        for loc in sub_root.findall("sm:url/sm:loc", NS):
            if loc.text:
                all_urls.append(loc.text)
    unresolved: List[str] = []
    en_count = nl_count = legacy_count = 0
    for url in all_urls:
        if "/en/" in url:
            en_count += 1
        elif "/nl/" in url:
            nl_count += 1
        else:
            legacy_count += 1
        if url_to_dist_path_from_origin(url) is None:
            unresolved.append(url)
    has_root = (PROD_ORIGIN + "/") in all_urls
    findings = (str(len(all_urls)) + " URLs (" + str(en_count) + " /en/, " +
                str(nl_count) + " /nl/, " + str(legacy_count) + " legacy unprefixed); " +
                str(len(unresolved)) + " unresolved; bare root: " + ("YES" if has_root else "no"))
    if unresolved:
        emit("Sitemap accuracy", "FAIL", findings,
             details=["  unresolved: " + u for u in unresolved[:20]])
    elif legacy_count > 0 or has_root:
        legacy_ex = [u for u in all_urls if "/en/" not in u and "/nl/" not in u][:5]
        emit("Sitemap accuracy", "SOFT", findings,
             details=[
                 "  All URLs resolve, but legacy unprefixed paths leak through @astrojs/sitemap filter.",
                 "  Per i18n Decision 7, only /en/* and /nl/* should be enumerated.",
                 "  Fix: tighten filter in astro.config.mjs to exclude any URL not under /en/ or /nl/.",
                 "  Examples (first 5):",
             ] + ["    " + u for u in legacy_ex])
    else:
        emit("Sitemap accuracy", "PASS", findings)


# Check 7 — robots.txt

def check_robots_txt() -> None:
    p = DIST / "robots.txt"
    if not p.exists():
        emit("Robots.txt", "FAIL", "robots.txt missing")
        return
    txt = p.read_text(encoding="utf-8")
    has_allow = re.search(r"Allow:\s*/", txt) is not None
    has_ua = re.search(r"User-agent:\s*\*", txt) is not None
    has_sm = ("Sitemap: " + PROD_ORIGIN + "/sitemap-index.xml") in txt
    if has_allow and has_ua and has_sm:
        emit("Robots.txt", "PASS", "Production policy emitted (User-agent: *, Allow: /, Sitemap pointer correct)")
    else:
        emit("Robots.txt", "FAIL",
             "missing element(s): allow=" + str(has_allow) + ", user_agent=" + str(has_ua) + ", sitemap=" + str(has_sm),
             details=["  contents:\n" + txt])


# Check 8 — zero-byte HTML

def check_zero_byte_html() -> None:
    empties = sorted([str(p.relative_to(DIST)) for p in iter_html_files() if p.stat().st_size == 0])
    if not empties:
        emit("Zero-byte HTML", "PASS", "no empty HTML files in dist/")
    else:
        emit("Zero-byte HTML", "FAIL",
             str(len(empties)) + " zero-byte HTML files (build emitted empty pages — render error swallowed)",
             details=["  " + e for e in empties])


# Check 9 — sidebar legacy /history/ link

def check_sidebar_legacy_links() -> None:
    samples = [DIST / "en" / "about" / "index.html", DIST / "nl" / "about" / "index.html"]
    found = []
    for s in samples:
        if not s.exists():
            continue
        parser = parse_html(s)
        if any(h == "/history/" or h.startswith("/history/") for h in parser.anchors):
            found.append(str(s.relative_to(DIST)))
    if not found:
        emit("Sidebar legacy /history/ link", "PASS", "Sidebar emits language-prefixed history hrefs")
    else:
        legacy_target = DIST / "history" / "index.html"
        emit("Sidebar legacy /history/ link", "SOFT",
             "Sidebar.astro still emits /history/ on " + str(len(found)) + " content pages " +
             "(legacy stub " + ("exists" if legacy_target.exists() else "MISSING") + " at dist/history/). "
             "4.7 §9e carryover; cosmetic — Caddy 301 covers production. (See Internal-404 check for the "
             "/history/final-2024/ sidebar entry, which is a real broken link.)",
             details=["  " + x for x in found])


# Verdict

def verdict() -> Tuple[str, int]:
    fails = [c for c in CHECKS if c.status == "FAIL"]
    softs = [c for c in CHECKS if c.status == "SOFT"]
    if fails:
        return "SHIP-BLOCKING", 1
    if softs:
        return "ACCEPTABLE WITH CAVEATS", 0
    return "SHIP-READY", 0


def write_report(report_path: Path, runtime_ms: int) -> None:
    today = dt.date.today().isoformat()
    lines: List[str] = []
    lines.append("# Link Integrity Report")
    lines.append("")
    lines.append("**Generated:** " + today)
    lines.append("**Build:** dist/ (output of `npm run build`, per step 4.7)")
    lines.append("**Step:** 4.8 Bilingual link integrity")
    lines.append("**Scripts:**")
    lines.append("- `scripts/check_links.mjs` (linkinator wrapper)")
    lines.append("- `scripts/verify_bilingual_integrity.py` (this verifier)")
    lines.append("")
    v, _ = verdict()
    lines.append("## Verdict: **" + v + "**")
    lines.append("")
    if v == "SHIP-READY":
        lines.append("All checks PASS or are catalogued/soft-flagged. The bilingual v1.1 baseline is ready to merge to main, deploy to GH Pages, and cut over to the Strato VPS at step 3.4.")
    elif v == "ACCEPTABLE WITH CAVEATS":
        lines.append("All hard checks PASS; catalogued asymmetries and 4.7/4.4 carryovers surface as SOFT findings. The bilingual v1.1 baseline is ship-acceptable with the documented caveats.")
    else:
        lines.append("One or more hard checks FAILED. See the Detailed findings section for upstream tickets to raise before merging.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| # | Check | Status | Findings |")
    lines.append("|---|---|---|---|")
    for i, c in enumerate(CHECKS, 1):
        f = c.findings.replace("|", "\\|")
        if len(f) > 220:
            f = f[:217] + "..."
        lines.append("| " + str(i) + " | " + c.name + " | " + c.status + " | " + f + " |")
    lines.append("")
    n_pass = sum(1 for c in CHECKS if c.status == "PASS")
    n_fail = sum(1 for c in CHECKS if c.status == "FAIL")
    n_soft = sum(1 for c in CHECKS if c.status == "SOFT")
    n_skip = sum(1 for c in CHECKS if c.status == "SKIP")
    lines.append("**Totals:** PASS " + str(n_pass) + "  FAIL " + str(n_fail) + "  SOFT " + str(n_soft) + "  SKIP " + str(n_skip))
    lines.append("")
    lines.append("**Verifier runtime:** " + str(round(runtime_ms / 1000.0, 2)) + "s")
    lines.append("")
    lines.append("## Detailed findings")
    lines.append("")
    for c in CHECKS:
        lines.append("### " + c.status + " - " + c.name)
        lines.append("")
        lines.append(c.findings)
        lines.append("")
        if c.details:
            lines.append("```")
            for d in c.details:
                lines.append(d)
            lines.append("```")
            lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("Catalogued or carryover findings (not regressions); listed for the audit trail.")
    lines.append("")
    if n_soft == 0 and n_skip == 0:
        lines.append("None.")
    else:
        for c in CHECKS:
            if c.status in ("SOFT", "SKIP"):
                lines.append("- **" + c.name + " (" + c.status + ")**: " + c.findings)
    lines.append("")
    lines.append("## Idempotency")
    lines.append("")
    lines.append("The verifier is deterministic: HTML files are walked in sorted order, all finding lists are sorted before emit, sampling uses a fixed seed (20260428). Two consecutive runs produce byte-identical reports apart from the `Generated:` date and `runtime` line.")
    lines.append("")
    lines.append("## Out of scope")
    lines.append("")
    lines.append("- Live-site crawling on aiact.annotated.nl (post-merge follow-up).")
    lines.append("- HTTP liveness check for external URLs (EUR-Lex, gdpr.annotated.nl) - format only.")
    lines.append("- Performance / Lighthouse / visual regression / accessibility / Pagefind index validation.")
    lines.append("")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    if not DIST.exists():
        print("ERROR: dist/ not found at " + str(DIST), file=sys.stderr)
        return 2
    print("[verify_bilingual_integrity] Step 4.8")
    print("[verify_bilingual_integrity] dist=" + str(DIST))
    print()
    catalogue = load_catalogued_dh_asymmetries()
    print("[catalogue] EN-missing: " + str(len(catalogue["en_missing"])) +
          "; NL-missing: " + str(len(catalogue["nl_missing"])))
    print()
    t0 = time.time()
    if args.fast:
        emit("Internal 404s", "SKIP", "--fast: skipped")
    else:
        check_internal_404s()
    check_hreflang_roundtrips(catalogue)
    check_decision_3_disclosures(catalogue)
    check_internal_reference_wraps()
    check_external_url_format()
    check_sitemap()
    check_robots_txt()
    check_zero_byte_html()
    check_sidebar_legacy_links()
    runtime_ms = int((time.time() - t0) * 1000)
    print()
    n_pass = sum(1 for c in CHECKS if c.status == "PASS")
    n_fail = sum(1 for c in CHECKS if c.status == "FAIL")
    n_soft = sum(1 for c in CHECKS if c.status == "SOFT")
    n_skip = sum(1 for c in CHECKS if c.status == "SKIP")
    print("[verify_bilingual_integrity] PASS " + str(n_pass) + "  FAIL " + str(n_fail) +
          "  SOFT " + str(n_soft) + "  SKIP " + str(n_skip) +
          "  runtime " + str(round(runtime_ms / 1000.0, 2)) + "s")
    v, exit_code = verdict()
    print("[verify_bilingual_integrity] Verdict: " + v)
    if not args.no_write:
        today = dt.date.today().isoformat()
        report_path = args.report or (REF_DIR / ("link-integrity-report-" + today + ".md"))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(report_path, runtime_ms)
        print("[verify_bilingual_integrity] Report: " + str(report_path))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
