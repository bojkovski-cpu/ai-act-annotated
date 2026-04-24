#!/usr/bin/env python3
"""
ingest_guidance.py — Stack-agnostic parser for AI Act guidance documents.

Reads a source document (PDF for now, HTML/DOCX as extensions land) and emits a
clean intermediate form under --out:

    {out}/{slug}/
    ├── source/{slug}_{lang}.pdf      (copied from --source)
    ├── source/checksums.txt
    ├── parsed/{slug}_{lang}.md        (clean markdown body + footnotes)
    ├── parsed/sections.json           (heading tree)
    ├── references/article_references.json   (AI Act citations only)
    └── manifest.json                  (GDPR-schema-compatible metadata)

See control-room/deployment/step-5.5a-handoff.md for the full spec. This script
is parameterised for reuse across later guidance steps (5.6+).

Usage:
    python3 ingest_guidance.py \
        --source /path/to/ai-act-guide.pdf \
        --lang en \
        --canonical-id nl_ez_aiact_guide_2025_v1_1 \
        --source-shortcode member_state \
        --document-type guide \
        --title-en "AI Act Guide" \
        --adoption-date 2025-09-02 \
        --url https://www.rijksoverheid.nl/... \
        --out /tmp/ai-act-guidance-intermediate

Parser choices:
  - PDF: pdfplumber (preserves layout — important for footnote/header separation).
  - HTML / DOCX: not yet implemented; stubs raise NotImplementedError so a later
    chat can extend without redesigning the manifest schema.

Idempotency:
  - Output files are written with sorted JSON keys and deterministic section IDs
    so a re-run on the same input produces byte-identical outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

# Soft hyphen, zero-width joiners, non-breaking space, ligatures — the usual
# PDF extraction debris that breaks regex matching.
_NORMALISE_MAP = {
    "\u00ad": "",       # soft hyphen
    "\u200b": "",       # zero-width space
    "\u200c": "",       # zero-width non-joiner
    "\u200d": "",       # zero-width joiner
    "\ufeff": "",       # BOM
    "\u00a0": " ",      # non-breaking space
    "\u2009": " ",      # thin space
    "\u202f": " ",      # narrow no-break space
    "\u2013": "-",      # en dash -> hyphen (keep semantic dashes? debatable; for citations we want plain hyphens)
    "\u2014": "—",      # em dash keeps
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    # Curly quotes -> straight (helps regex)
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}


def normalise_text(s: str) -> str:
    if not s:
        return ""
    # NFC for consistent combining
    s = unicodedata.normalize("NFC", s)
    for k, v in _NORMALISE_MAP.items():
        s = s.replace(k, v)
    # Collapse runs of spaces but preserve newlines
    s = re.sub(r"[ \t]+", " ", s)
    return s


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------

@dataclass
class Page:
    number: int                      # 1-based
    lines: list[str] = field(default_factory=list)
    footnote_lines: list[str] = field(default_factory=list)


# Running-header pattern for the EZ AI Act Guide:
#   "AI Act Guide | Step 1  4"
#   "AI Act Guide |   2"
#   "AI Act Guide | Guide to reading and disclaimer  3"
# Generalise to: a short line starting with the title followed by " | ".
_RUNNING_HEADER_RE = re.compile(r"^\s*[A-Z][A-Za-z0-9 :\-',]{0,60}\s+\|\s+.{0,80}\s+\d+\s*$")

# Footnote line heuristic: line starts with a number (1-3 digits) followed by
# whitespace, and the number is small (<= 300). This is imperfect but works for
# numbered footnotes at page bottom.
_FOOTNOTE_LINE_RE = re.compile(r"^\s*(\d{1,3})\s+(.+)$")


def extract_pages(pdf_path: Path) -> list[Page]:
    import pdfplumber

    pages: list[Page] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            # Use default extraction; pdfplumber returns lines preserving order.
            raw = p.extract_text(x_tolerance=2, y_tolerance=3) or ""
            raw = normalise_text(raw)
            lines = [ln.rstrip() for ln in raw.split("\n") if ln.strip()]

            body: list[str] = []
            footnotes: list[str] = []

            # Two-pass: first drop running headers, then split body vs footnotes.
            cleaned = [ln for ln in lines if not _RUNNING_HEADER_RE.match(ln)]

            # Split body vs footnotes: heuristic — footnotes are a tail block of
            # lines where the first line starts with a footnote number. We look
            # for the LAST contiguous block at the end of the page that matches
            # the footnote pattern.
            split_idx = len(cleaned)
            for idx in range(len(cleaned) - 1, -1, -1):
                ln = cleaned[idx]
                m = _FOOTNOTE_LINE_RE.match(ln)
                if m and int(m.group(1)) <= 300:
                    split_idx = idx
                else:
                    # Continuation lines of a footnote are also OK — keep
                    # walking up while the line does not look like body text.
                    # A body paragraph usually starts with a capital letter and
                    # is longer than ~40 chars; a footnote continuation is
                    # shorter and doesn't have a leading number but follows a
                    # numbered footnote above.
                    if split_idx < len(cleaned) and len(ln) < 120 and not re.match(r"^[A-Z][a-z]{3,}", ln):
                        continue
                    break

            body = cleaned[:split_idx]
            footnotes = cleaned[split_idx:]

            pages.append(Page(number=i, lines=body, footnote_lines=footnotes))
    return pages


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Step heading: "Step 1. (Risk) ..." (en) or "Stap 1. (Risico) ..." (nl)
_STEP_HEADING_RE = re.compile(r"^(?:Step|Stap)\s+(\d+)\.\s+(.+?)\s*$")
_STEP_LABEL_BY_LANG = {"en": "Step", "nl": "Stap"}
# Sub-section heading like "1.3. General purpose AI models and AI systems"
_SUBSECTION_RE = re.compile(r"^(\d+\.\d+)\.\s+(.+?)\s*$")
# Dutch forward-reference marker (inline cross-references in body text)
_FORWARD_REF_MARKERS = (" on page ", " op pagina ")
# "Requirements for high-risk AI systems", "Obligations for deployers of ..."
# etc. — these are narrative headings; detect by isolation + Title Case + short.


@dataclass
class Section:
    id: str              # slug-like deterministic id
    level: int           # 1 = step, 2 = sub-section, 3 = sub-heading
    number: str | None   # "1", "1.3", or None for narrative heads
    title: str
    page: int            # first page the section appears on
    body: list[str] = field(default_factory=list)   # paragraph strings


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:80]


def _looks_like_heading_continuation(ln: str) -> bool:
    """Heuristic: a wrapped heading continuation is short, title-cased or
    lowercase, has no trailing period before a ? mark, and does not start a new
    paragraph marker (bullet, number, heading). Step titles end with ? in this
    doc."""
    if not ln or len(ln) > 80:
        return False
    if ln.startswith(("• ", "- ", "* ")):
        return False
    if re.match(r"^\d+[\.\)]\s", ln):
        return False
    # A continuation is typically a sub-clause ending with ? or .
    return bool(re.match(r"^[A-Za-z(\"'].*[\?\.]$", ln))


def build_sections(pages: list[Page], lang: str = "en") -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    step_label = _STEP_LABEL_BY_LANG.get(lang, "Step")

    def flush():
        nonlocal current
        if current is not None:
            sections.append(current)

    for p in pages:
        i = 0
        while i < len(p.lines):
            ln = p.lines[i]
            m_step = _STEP_HEADING_RE.match(ln)
            m_sub = _SUBSECTION_RE.match(ln)

            # Reject inline forward-references like:
            #   "4.3. General purpose AI models and systems on page 18"
            #   "see 1.2. High-risk AI systems on page 5"
            sub_is_real = False
            if m_sub:
                body_part = m_sub.group(2)
                body_lower = body_part.lower()
                # Forward-references always contain "on page" / "op pagina"; exclude.
                if any(marker in body_lower for marker in _FORWARD_REF_MARKERS):
                    sub_is_real = False
                # Inline reference joined with another ("... on page 13 and 4.3. ..."):
                # the body_part will contain another numbered section reference.
                elif re.search(r"\b\d+\.\d+\.\s+", body_part):
                    sub_is_real = False
                else:
                    sub_is_real = True

            # Reject inline forward-references to step headings like:
            #   "Stap 3. Zijn wij de aanbieder of gebruiksverantwoordelijke ... op pagina 12"
            step_is_real = False
            if m_step:
                step_body = m_step.group(2)
                step_body_lower = step_body.lower()
                if any(marker in step_body_lower for marker in _FORWARD_REF_MARKERS):
                    step_is_real = False
                else:
                    step_is_real = True

            if m_step and step_is_real:
                flush()
                num = m_step.group(1)
                title = m_step.group(2).strip()
                # Look ahead for wrapped continuation
                if i + 1 < len(p.lines) and _looks_like_heading_continuation(p.lines[i + 1]):
                    title = (title + " " + p.lines[i + 1].strip()).strip()
                    i += 1
                current = Section(
                    id=f"step-{num}-{slugify(title)}"[:100],
                    level=1, number=num, title=f"{step_label} {num}. {title}", page=p.number,
                )
            elif m_sub and sub_is_real:
                flush()
                num = m_sub.group(1)
                title = m_sub.group(2).strip()
                if i + 1 < len(p.lines) and _looks_like_heading_continuation(p.lines[i + 1]):
                    title = (title + " " + p.lines[i + 1].strip()).strip()
                    i += 1
                current = Section(
                    id=f"sec-{num.replace('.', '-')}-{slugify(title)}"[:100],
                    level=2, number=num, title=f"{num}. {title}", page=p.number,
                )
            else:
                if current is None:
                    # Pre-amble before first step (title page, disclaimer, etc.)
                    current = Section(
                        id="frontmatter",
                        level=1, number=None, title="Frontmatter", page=p.number,
                    )
                current.body.append(ln)
            i += 1
    flush()
    return sections


# ---------------------------------------------------------------------------
# Footnote consolidation
# ---------------------------------------------------------------------------

@dataclass
class Footnote:
    number: int
    text: str
    page: int


def build_footnotes(pages: list[Page]) -> dict[int, Footnote]:
    """
    Walk each page's footnote_lines and assemble a {number -> Footnote} dict.
    Handles footnote text that wraps across multiple lines. A new footnote
    starts on a line beginning with a number followed by whitespace.
    """
    footnotes: dict[int, Footnote] = {}
    for p in pages:
        cur: Footnote | None = None
        for ln in p.footnote_lines:
            m = _FOOTNOTE_LINE_RE.match(ln)
            if m and int(m.group(1)) <= 300:
                # Heuristic: accept only if the number is > last-seen or close.
                n = int(m.group(1))
                rest = m.group(2).strip()
                if cur is not None:
                    footnotes[cur.number] = cur
                cur = Footnote(number=n, text=rest, page=p.number)
            else:
                if cur is not None:
                    cur.text = (cur.text + " " + ln.strip()).strip()
        if cur is not None:
            footnotes[cur.number] = cur
    return footnotes


# ---------------------------------------------------------------------------
# Article reference extraction
# ---------------------------------------------------------------------------

# AI Act article citation patterns. English primary; Dutch as fallback.
# Matches:
#   Article 5(1)(a)
#   Article 5 (1) (a)
#   Article 5(1), point (a)
#   Articles 22, 23 and 24
#   Article 3(5), (6) and (7)
_ART_EN_RE = re.compile(
    r"\b(?:Articles?|Artikel(?:en)?)\s+"         # Article(s) EN or Artikel(en) NL
    r"(\d{1,3})"                              # article number
    r"(?:\s*\(\s*(\d+[a-z]?)\s*\))?"         # optional paragraph, e.g. (1) or (1a)
    r"(?:\s*(?:,\s*point\s+)?\(\s*([a-z])\s*\))?",  # optional letter (a) or point (a)
    re.IGNORECASE,
)

# Extended: "Article 3(5), (6) and (7)" — paragraph-only follow-ons.
_ART_EN_EXTRAS_RE = re.compile(
    r"(?:,\s*\(\s*(\d+[a-z]?)\s*\)|\s*(?:and|en)\s*\(\s*(\d+[a-z]?)\s*\))",
    re.IGNORECASE,
)

# "Articles 22, 23 and 24" / "Artikelen 22, 23 en 24" — list form.
_ART_LIST_RE = re.compile(
    r"\b(?:Articles|Artikelen)\s+(\d{1,3})(?:\s*,\s*(\d{1,3}))?(?:\s*,\s*(\d{1,3}))?(?:\s*(?:and|en)\s*(\d{1,3}))?",
    re.IGNORECASE,
)

_ART_NL_RE = re.compile(
    r"\bartikel(?:en)?\s+"
    r"(\d{1,3})"
    r"(?:,?\s+lid\s+(\d+))?"
    r"(?:,?\s+onder\s+([a-z]))?",
    re.IGNORECASE,
)


# Scope anchor — only treat a citation as AI-Act-bound if it appears in a
# sentence/footnote that mentions the Act, OR it is in a footnote (the EZ guide
# puts all AI Act cites in footnotes that say "... AI Act.").
_AI_ACT_SCOPE_RE = re.compile(
    r"(AI\s*Act|Regulation\s*\(EU\)\s*2024/1689|AI[-\s]*verordening)",
    re.IGNORECASE,
)


@dataclass
class ArticleRef:
    location_in_doc: dict
    target_kind: str           # "article"
    target_article: int
    target_paragraph: str | None
    target_letter: str | None
    target_subparagraph: str | None
    raw_citation: str
    surrounding_context: str


def _find_section_for_page(sections: list[Section], page: int) -> Section | None:
    """Return the last section whose start page <= page."""
    candidate = None
    for s in sections:
        if s.page <= page:
            candidate = s
        else:
            break
    return candidate


def extract_article_refs(
    pages: list[Page],
    sections: list[Section],
    footnotes: dict[int, Footnote],
    lang: str,
) -> list[ArticleRef]:
    """
    Strategy for the EZ AI Act Guide (footnote-heavy):
      1. Walk each footnote; if its text mentions "AI Act" (or "AI-verordening"
         in NL), extract all Article citations from that footnote.
      2. Also scan body text for explicit "AI Act" scope mentions — the doc
         does say things like "Article 50 AI Act" inline too.

    Out-of-scope citations (other regulations, product directives) are
    filtered by the scope anchor.
    """
    refs: list[ArticleRef] = []

    # Pass 1: footnotes
    for fn_num, fn in footnotes.items():
        if not _AI_ACT_SCOPE_RE.search(fn.text):
            continue
        _collect_from_text(
            text=fn.text,
            page=fn.page,
            section=_find_section_for_page(sections, fn.page),
            footnote_num=fn_num,
            out=refs,
            context=fn.text,
            lang=lang,
        )

    # Pass 2: body text — only within sentences that have the scope anchor
    for p in pages:
        body = " ".join(p.lines)
        if not _AI_ACT_SCOPE_RE.search(body):
            continue
        # Rough sentence split; good enough for context extraction
        for sentence in re.split(r"(?<=[\.\!\?])\s+", body):
            if not _AI_ACT_SCOPE_RE.search(sentence):
                continue
            _collect_from_text(
                text=sentence,
                page=p.number,
                section=_find_section_for_page(sections, p.number),
                footnote_num=None,
                out=refs,
                context=sentence,
                lang=lang,
            )

    # Dedupe by (location, target) only — raw_citation can vary by regex
    # (e.g. "Artikel 50" vs "artikel 50") for the same semantic reference.
    seen = set()
    uniq: list[ArticleRef] = []
    for r in refs:
        key = (
            r.location_in_doc.get("page"),
            r.location_in_doc.get("footnote"),
            r.location_in_doc.get("section"),
            r.target_article,
            r.target_paragraph,
            r.target_letter,
        )
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    # Filter out-of-range
    uniq = [r for r in uniq if 1 <= r.target_article <= 113]
    return uniq


def _collect_from_text(
    text: str,
    page: int,
    section: Section | None,
    footnote_num: int | None,
    out: list[ArticleRef],
    context: str,
    lang: str,
) -> None:
    # Shorten context to ~2-3 sentences / 400 chars
    ctx = context.strip()
    if len(ctx) > 400:
        ctx = ctx[:400].rsplit(" ", 1)[0] + "…"

    loc = {
        "section": section.number if section and section.number else (section.id if section else None),
        "page": page,
        "footnote": footnote_num,
    }

    # Record character spans already covered so that list-form matches take
    # precedence over overlapping primary-form matches (avoids double-counting
    # "Articles 26 and 27" as Art 26 [list] + Art 27 [list] + Art 26 [primary]).
    covered_spans: list[tuple[int, int]] = []

    def _overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in covered_spans)

    # List form: "Articles 22, 23 and 24"
    for m in _ART_LIST_RE.finditer(text):
        nums = [g for g in m.groups() if g]
        if len(nums) >= 2:
            raw = m.group(0)
            covered_spans.append(m.span())
            for n in nums:
                out.append(ArticleRef(
                    location_in_doc=loc,
                    target_kind="article",
                    target_article=int(n),
                    target_paragraph=None,
                    target_letter=None,
                    target_subparagraph=None,
                    raw_citation=raw,
                    surrounding_context=ctx,
                ))

    # Primary form: "Article N(p)(l)" — skip if already covered by a list match
    for m in _ART_EN_RE.finditer(text):
        if _overlaps(*m.span()):
            continue
        n = int(m.group(1))
        para = m.group(2)
        letter = m.group(3)
        raw = m.group(0)
        out.append(ArticleRef(
            location_in_doc=loc,
            target_kind="article",
            target_article=n,
            target_paragraph=para,
            target_letter=letter,
            target_subparagraph=None,
            raw_citation=raw,
            surrounding_context=ctx,
        ))
        # Follow-on paragraphs: "Article 3(5), (6) and (7)"
        tail = text[m.end(): m.end() + 120]
        for m2 in _ART_EN_EXTRAS_RE.finditer(tail):
            extra = m2.group(1) or m2.group(2)
            if extra:
                out.append(ArticleRef(
                    location_in_doc=loc,
                    target_kind="article",
                    target_article=n,
                    target_paragraph=extra,
                    target_letter=None,
                    target_subparagraph=None,
                    raw_citation=f"Article {n}({extra})",
                    surrounding_context=ctx,
                ))

    # Dutch "artikel X, lid Y, onder z" form — only emit when not already
    # covered by the primary regex (which handles the parenthetical form).
    if lang == "nl":
        for m in _ART_NL_RE.finditer(text):
            if _overlaps(*m.span()):
                continue
            # Also skip pure bare-form "artikel N" matches that the primary
            # regex already emitted — those have lid=None and onder=None AND
            # overlap with a primary match at the same article number.
            if not m.group(2) and not m.group(3):
                # Check if a primary emission already captured this article at this location
                art = int(m.group(1))
                if any(r.target_article == art and r.location_in_doc == loc for r in out):
                    continue
            out.append(ArticleRef(
                location_in_doc=loc,
                target_kind="article",
                target_article=int(m.group(1)),
                target_paragraph=m.group(2),
                target_letter=m.group(3),
                target_subparagraph=None,
                raw_citation=m.group(0),
                surrounding_context=ctx,
            ))


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(sections: list[Section], footnotes: dict[int, Footnote], meta: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {meta['title']['en']}")
    lines.append("")
    lines.append(f"_Intermediate parse — source: {meta['canonical_id']} — not for publication._")
    lines.append("")

    for s in sections:
        if s.id == "frontmatter":
            # Still include it, but flag it
            lines.append(f"<!-- Frontmatter (pre-Step 1) — page {s.page} -->")
            lines.append("")
        header_hashes = "#" * (s.level + 1)   # level 1 -> "##", level 2 -> "###"
        lines.append(f"{header_hashes} {s.title}")
        lines.append("")
        # Each consecutive non-empty body line is treated as continuing the
        # same paragraph; blank lines split paragraphs. pdfplumber strips blank
        # lines aggressively, so we heuristically split on bullets / numbering.
        para_buf: list[str] = []
        for b in s.body:
            if b.startswith(("• ", "- ", "* ")):
                if para_buf:
                    lines.append(" ".join(para_buf))
                    lines.append("")
                    para_buf = []
                lines.append(b)
            elif re.match(r"^\d+\.\s+", b):
                if para_buf:
                    lines.append(" ".join(para_buf))
                    lines.append("")
                    para_buf = []
                lines.append(b)
            else:
                para_buf.append(b)
        if para_buf:
            lines.append(" ".join(para_buf))
            lines.append("")

    # Footnotes
    if footnotes:
        lines.append("---")
        lines.append("")
        lines.append("## Footnotes")
        lines.append("")
        for n in sorted(footnotes.keys()):
            lines.append(f"[^{n}]: {footnotes[n].text}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest an AI Act guidance document to a stack-agnostic intermediate form.")
    ap.add_argument("--source", required=True, type=Path, help="Path to source file (PDF/HTML/DOCX).")
    ap.add_argument("--lang", required=True, choices=["en", "nl"], help="Language of source.")
    ap.add_argument("--canonical-id", required=True, help="Canonical doc id, e.g. nl_ez_aiact_guide_2025_v1_1.")
    ap.add_argument("--out", required=True, type=Path, help="Output root directory.")
    ap.add_argument("--source-shortcode", required=True,
                    choices=["commission", "ai_office", "edpb", "member_state", "other"],
                    help="Issuer category per handoff manifest schema.")
    ap.add_argument("--document-type", required=True,
                    choices=["guideline", "opinion", "recommendation", "code_of_practice", "faq", "guide", "other"],
                    help="Document type per handoff manifest schema.")
    ap.add_argument("--title-en", required=True, help="English title for manifest.")
    ap.add_argument("--title-nl", default=None, help="Dutch title for manifest (optional).")
    ap.add_argument("--adoption-date", required=True, help="YYYY-MM-DD.")
    ap.add_argument("--url", required=True, help="Source URL on issuer's site.")
    ap.add_argument("--entry-into-force", default=None, help="YYYY-MM-DD (optional).")
    args = ap.parse_args()

    src: Path = args.source.resolve()
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2

    if src.suffix.lower() != ".pdf":
        print(f"ERROR: only PDF parsing is implemented in this version; got {src.suffix}", file=sys.stderr)
        return 2

    slug = args.canonical_id
    out_root: Path = args.out.resolve() / slug
    src_dir = out_root / "source"
    parsed_dir = out_root / "parsed"
    refs_dir = out_root / "references"
    for d in (src_dir, parsed_dir, refs_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Copy source + checksum
    dest_src = src_dir / f"{slug}_{args.lang}{src.suffix.lower()}"
    if not dest_src.exists() or sha256_file(dest_src) != sha256_file(src):
        shutil.copy2(src, dest_src)
    checksum = sha256_file(dest_src)
    (src_dir / "checksums.txt").write_text(f"{checksum}  {dest_src.name}\n", encoding="utf-8")

    # Parse
    pages = extract_pages(src)
    sections = build_sections(pages, lang=args.lang)
    footnotes = build_footnotes(pages)

    # Manifest stub
    meta: dict[str, Any] = {
        "canonical_id": slug,
        "source": args.source_shortcode,
        "document_type": args.document_type,
        "title": {"en": args.title_en, "nl": args.title_nl},
        "adoption_date": args.adoption_date,
        "entry_into_force": args.entry_into_force,
        "end_of_validity": None,
        "endorsement_status": None,
        "supersedes": None,
        "language": args.lang,
        "url": args.url,
        "source_file_checksum": f"sha256:{checksum}",
        "page_count": len(pages),
        "paragraph_count": None,
        "citations_found": None,
    }

    refs = extract_article_refs(pages, sections, footnotes, lang=args.lang)

    md = render_markdown(sections, footnotes, meta)
    (parsed_dir / f"{slug}_{args.lang}.md").write_text(md, encoding="utf-8")

    md_body = md.split("\n## Footnotes\n", 1)[0]
    paragraph_count = sum(
        1
        for blk in re.split(r"\n\s*\n", md_body)
        if blk.strip() and not blk.lstrip().startswith(("#", "<!--", "---", "_"))
    )

    sections_payload = [
        {
            "id": s.id,
            "level": s.level,
            "number": s.number,
            "title": s.title,
            "page": s.page,
            "paragraph_count": len(s.body),
        }
        for s in sections
    ]
    # Language-suffixed outputs so EN and NL can coexist in the same doc folder.
    (parsed_dir / f"sections_{args.lang}.json").write_text(
        json.dumps(sections_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    refs_payload = [asdict(r) for r in refs]
    (refs_dir / f"article_references_{args.lang}.json").write_text(
        json.dumps(refs_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Build per-language stats block
    per_lang = {
        "source_file": dest_src.name,
        "source_file_checksum": f"sha256:{checksum}",
        "page_count": len(pages),
        "paragraph_count": paragraph_count,
        "citations_found": len(refs_payload),
        "section_count": len(sections_payload),
        "footnote_count": len(footnotes),
    }

    # Manifest merge: if manifest.json already exists, preserve other languages.
    manifest_path = out_root / "manifest.json"
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    # Top-level fields (language-agnostic)
    existing_title = existing.get("title") or {}
    final = {
        "canonical_id": slug,
        "source": args.source_shortcode,
        "document_type": args.document_type,
        "title": {
            "en": args.title_en if args.lang == "en" else existing_title.get("en"),
            "nl": (
                args.title_nl if args.title_nl
                else (args.title_en if args.lang == "nl" else existing_title.get("nl"))
            ),
        },
        "adoption_date": args.adoption_date,
        "entry_into_force": args.entry_into_force,
        "end_of_validity": existing.get("end_of_validity"),
        "endorsement_status": existing.get("endorsement_status"),
        "supersedes": existing.get("supersedes"),
        "url": args.url,
    }

    by_lang = dict(existing.get("by_language") or {})
    by_lang[args.lang] = per_lang
    final["by_language"] = by_lang
    final["languages"] = sorted(by_lang.keys())

    manifest_path.write_text(
        json.dumps(final, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"[ok] wrote {out_root} (lang={args.lang})")
    print(
        f"     pages={len(pages)} sections={len(sections)} "
        f"footnotes={len(footnotes)} citations={len(refs_payload)} paragraphs={paragraph_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
