"""
parse_aiact_nl_historical.py — Step 4.3a parsers for Commission 2021 and Parliament 2023.

Two distinct HTML templates, two distinct intermediate shapes:

- commission-2021 (CELEX 52021PC0206) — a Word-style export. Articles, recitals,
  annexes in flat paragraphs classified by Word style (Titrearticle, ManualConsidrant,
  Annexetitre, Normal, li Point1, etc.). Produces articles/recitals/annexes.

- parliament-2023 (CELEX 52023AP0236) — a list of 771 numbered amendments in a
  four-column EUR-Lex comparison format (original text vs Parliament amendment).
  Produces amendment-NNN.md, each containing the amendment's target heading and the
  Commission-vs-Parliament column pair.

Filenames follow the existing English history corpus: unpadded numbers
(article-1, recital-1). Annexes use lowercase roman (annex-i, annex-ii, ...).
Amendments use 3-digit padding (amendment-001 .. amendment-771).
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

LANGUAGE = "nl"

SOURCES = {
    "commission-2021": {
        "celex": "52021PC0206",
        "url": "https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:52021PC0206",
        "label": "European Commission proposal (April 2021) — COM(2021) 206 final",
    },
    "parliament-2023": {
        "celex": "52023AP0236",
        "url": "https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:52023AP0236",
        "label": "European Parliament position (14 June 2023) — P9_TA(2023)0236",
    },
}

ROMAN = {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9,
         "X":10,"XI":11,"XII":12,"XIII":13,"XIV":14,"XV":15}

NBSP = re.compile("\u00a0")
MULTI = re.compile(r"[ \t]{2,}")
NUM_LEAD = re.compile(r"^(\d+)\.\s+")


def clean(t: str) -> str:
    t = NBSP.sub(" ", t or "")
    t = MULTI.sub(" ", t)
    return t.strip()

def ptext(p) -> str:
    return clean(p.get_text(" ", strip=True)) if p is not None else ""

def yaml_escape(s: str) -> str:
    if s is None:
        return '""'
    return f'"{s.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"'

def frontmatter(d: dict) -> str:
    out = ["---"]
    for k, v in d.items():
        if v is None:
            out.append(f"{k}: null")
        elif isinstance(v, bool):
            out.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, int):
            out.append(f"{k}: {v}")
        elif isinstance(v, str):
            out.append(f"{k}: {yaml_escape(v)}")
        else:
            out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    out.append("---")
    return "\n".join(out) + "\n"


# =============================================================================
# Commission 2021
# =============================================================================

COMM_LIST_ITEM_CLASSES = {"li Point1","li Point0","li Point2","li Point1letter","li ManualPointlet","li Point3"}
COMM_NUM_PARA_CLASSES  = {"li NumPar1","li ManualNumPar1","li NumPar2","li ManualNumPar2"}

@dataclass
class CommArticle:
    number: int; title: str
    titel_roman: str; titel_num: int; titel_title: str
    hoofdstuk_num: int | None; hoofdstuk_title: str | None
    body_md: str; body_text: str; char_count: int

@dataclass
class CommRecital:
    number: int; body: str; char_count: int

@dataclass
class CommAnnex:
    roman: str; arabic: int; title: str; body_md: str; body_text: str; char_count: int


def _p_to_md(p: Tag) -> str:
    """Convert a Commission-2021 body paragraph to markdown."""
    cls = " ".join(p.get("class") or [])
    txt = ptext(p)
    if not txt:
        return ""
    if cls in COMM_LIST_ITEM_CLASSES:
        # "(a) ..." or "(i) ..." etc — already has its own marker prefix; render as list item
        # Add indent for deeper points
        indent = ""
        if "Point2" in cls or "Point1letter" in cls or "ManualPointlet" in cls:
            indent = "  "
        elif "Point3" in cls:
            indent = "    "
        return f"{indent}- {txt}"
    if cls in COMM_NUM_PARA_CLASSES:
        m = NUM_LEAD.match(txt)
        if m:
            return f"**{m.group(1)}.** {txt[m.end():]}"
        return txt
    # SectionTitle would be a heading; skip inside article bodies (article bodies shouldn't contain them)
    if "SectionTitle" in cls:
        return f"### {txt}"
    # Normal / Text1 / everything else → plain paragraph
    return txt


def _collect_body(start: Tag, stop_classes: list[str]) -> list[Tag]:
    """Collect sibling elements after `start`, stopping when any element has a class in stop_classes."""
    out = []
    sib = start.next_sibling
    while sib is not None:
        if isinstance(sib, Tag):
            c = " ".join(sib.get("class") or [])
            if any(s == c or s in (sib.get("class") or []) for s in stop_classes):
                break
            out.append(sib)
        sib = sib.next_sibling
    return out


def _structural_context_for(node: Tag):
    """Walk back through SectionTitle paragraphs to find the current TITEL and Hoofdstuk."""
    titel_roman, titel_num, titel_title = "", 0, ""
    hoofd_num, hoofd_title = None, None
    seen_titel = False
    seen_hoofd = False
    for prev in node.find_all_previous(class_="SectionTitle"):
        txt = ptext(prev)
        # Top-level TITEL marker: "TITEL I" etc.
        m = re.match(r"^TITEL\s+([IVXLC]+)$", txt, re.IGNORECASE)
        if m and not seen_titel:
            titel_roman = m.group(1).upper()
            titel_num = ROMAN.get(titel_roman, 0)
            # The title text is the IMMEDIATELY-following SectionTitle paragraph.
            nxt = prev.find_next(class_="SectionTitle")
            if nxt is not None and nxt is not prev:
                titel_title = ptext(nxt)
            seen_titel = True
            # continue walking back in case a hoofdstuk was set between this and node; but since we walk back,
            # the FIRST TITEL we see is the enclosing one, and we've likely already seen the hoofd below.
            break
        mh = re.match(r"^(?:Hoofdstuk|HOOFDSTUK)\s+(\d+)$", txt)
        if mh and not seen_hoofd:
            hoofd_num = int(mh.group(1))
            nxt = prev.find_next(class_="SectionTitle")
            if nxt is not None and nxt is not prev:
                hoofd_title = ptext(nxt)
            seen_hoofd = True
            # keep walking to find TITEL
    return titel_roman, titel_num, titel_title, hoofd_num, hoofd_title


def parse_commission_2021(html_path: Path):
    with html_path.open(encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # -- Articles --
    articles = []
    titres = soup.find_all(class_="Titrearticle")
    for i, t in enumerate(titres):
        txt = ptext(t)
        m = re.match(r"^Artikel\s+(\d+)(?:\s+(.+))?$", txt)
        if not m:
            continue
        num = int(m.group(1))
        title = (m.group(2) or "").strip()
        # Body: siblings after t until next Titrearticle OR Annexetitre
        parts_md = []
        parts_text = []
        sib = t.next_sibling
        while sib is not None:
            if isinstance(sib, Tag):
                cls = sib.get("class") or []
                if "Titrearticle" in cls or "Annexetitre" in cls:
                    break
                if sib.name == "p":
                    md = _p_to_md(sib)
                    if md:
                        parts_md.append(md)
                    txt_ = ptext(sib)
                    if txt_:
                        parts_text.append(txt_)
                elif sib.name == "div":
                    # Shouldn't happen in this doc — flat structure — but handle just in case
                    t_ = ptext(sib)
                    if t_:
                        parts_text.append(t_)
                        parts_md.append(t_)
            sib = sib.next_sibling

        tr, tn, tt, hn, ht = _structural_context_for(t)
        body_md = "\n\n".join(parts_md).strip() + "\n"
        body_text = "\n\n".join(parts_text).strip()
        articles.append(CommArticle(num, title, tr, tn, tt, hn, ht, body_md, body_text, len(body_text)))

    # -- Recitals --
    recitals = []
    for el in soup.find_all(class_="li ManualConsidrant"):
        txt = ptext(el)
        m = re.match(r"^\((\d+)\)\s*(.*)$", txt, re.DOTALL)
        if not m:
            continue
        num = int(m.group(1))
        body = m.group(2).strip()
        recitals.append(CommRecital(num, body + "\n", len(body)))
    recitals.sort(key=lambda r: r.number)

    # -- Annexes --
    annexes = []
    annex_markers = soup.find_all(class_="Annexetitre")
    for i, el in enumerate(annex_markers):
        txt = ptext(el)
        m = re.match(r"^BIJLAGE\s+([IVX]+)\s*(.*)$", txt, re.DOTALL)
        if not m:
            continue
        roman = m.group(1)
        title = m.group(2).strip()
        arabic = ROMAN.get(roman)
        if not arabic:
            continue
        # Body: siblings after this Annexetitre until next Annexetitre
        parts_md = []
        parts_text = []
        sib = el.next_sibling
        while sib is not None:
            if isinstance(sib, Tag):
                cls = sib.get("class") or []
                if "Annexetitre" in cls:
                    break
                if sib.name == "p":
                    md = _p_to_md(sib)
                    if md:
                        parts_md.append(md)
                    t_ = ptext(sib)
                    if t_:
                        parts_text.append(t_)
                elif sib.name == "div":
                    # could contain tables in annex II — descend for text content
                    t_ = ptext(sib)
                    if t_:
                        parts_text.append(t_)
                        parts_md.append(t_)
                elif sib.name == "table":
                    # crude: flatten table text
                    rows = []
                    for tr_el in sib.find_all("tr"):
                        cells = [ptext(td) for td in tr_el.find_all(["td","th"])]
                        rows.append(" | ".join(c for c in cells if c))
                    tbl = "\n".join(r for r in rows if r)
                    if tbl:
                        parts_md.append(tbl)
                        parts_text.append(tbl)
            sib = sib.next_sibling
        body_md = "\n\n".join(parts_md).strip() + "\n"
        body_text = "\n\n".join(parts_text).strip()
        annexes.append(CommAnnex(roman, arabic, title, body_md, body_text, len(body_text)))

    articles.sort(key=lambda a: a.number)
    annexes.sort(key=lambda a: a.arabic)
    return articles, recitals, annexes


# =============================================================================
# Parliament 2023 — amendments
# =============================================================================

@dataclass
class Amendment:
    number: int
    target: str           # e.g. "Overweging 1" / "Artikel 4 bis (nieuw)" / "Bijlage III - punt 1 - letter a"
    commission_text: str  # left column — Commission's original
    parliament_text: str  # right column — Parliament's amendment
    body_md: str
    char_count: int


def _cells_as_text(row: Tag) -> list[str]:
    """Return text contents of all top-level cells in a row."""
    return [ptext(td) for td in row.find_all(["td","th"], recursive=False)]


def parse_parliament_2023(html_path: Path):
    """Walk grseq-1 'Amendement N' markers, collect the three following headings and the comparison table."""
    with html_path.open(encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Identify all grseq-1 paragraphs that start with "Amendement N" — these are the amendment anchors.
    grs = soup.find_all(class_="oj-ti-grseq-1")
    amendments: list[Amendment] = []
    i = 0
    while i < len(grs):
        g = grs[i]
        txt = ptext(g)
        m = re.match(r"^Amendement\s+(\d+)$", txt)
        if not m:
            i += 1
            continue
        num = int(m.group(1))
        # The NEXT grseq-1 usually says "Voorstel voor een verordening"; the one after is the target (e.g. "Overweging 1").
        # But sometimes that pattern changes. Collect the next 2-3 grseq-1 paragraphs until we hit a table or the next Amendement.
        target_parts = []
        j = i + 1
        while j < len(grs):
            t = ptext(grs[j])
            if re.match(r"^Amendement\s+\d+$", t):
                break
            target_parts.append(t)
            j += 1
            if len(target_parts) >= 4:
                break
        # The table containing the Commission-vs-Parliament comparison is after the grseq-1 paragraphs.
        # Find the next <table> after g (but before the next Amendement).
        next_amend = grs[j] if j < len(grs) else None
        table = None
        node = g
        while node is not None:
            node = node.find_next()
            if node is None: break
            if next_amend is not None and node is next_amend:
                break
            if isinstance(node, Tag) and node.name == "table":
                table = node
                break

        commission_text = ""
        parliament_text = ""
        if table is not None:
            # Expect a 2-column comparison. First <tr> may be a header.
            rows = table.find_all("tr")
            body_rows = []
            for tr in rows:
                cells = tr.find_all(["td","th"], recursive=False)
                if not cells:
                    cells = tr.find_all(["td","th"])
                texts = [ptext(c) for c in cells]
                # Skip the column-header row (present on every amendment table).
                joined = " | ".join(texts).lower().strip()
                if ("door de commissie voorgestelde tekst" in joined
                        or joined in ("amendement", "| amendement", "amendement |",
                                      "door de commissie voorgestelde tekst | amendement")):
                    continue
                # Skip fully-empty rows.
                if not any(texts):
                    continue
                if len(texts) == 2:
                    # Preserve empty cells as empty — a "(nieuw)" amendment has an empty Commission column
                    # and must NOT be duplicated into both sides.
                    body_rows.append([texts[0], texts[1]])
                elif len(texts) == 1:
                    # Truly single-cell row (e.g. spanned heading). Attach to both sides so it appears in context.
                    body_rows.append([texts[0], texts[0]])
                # rows with >2 cells are rare and ambiguous — ignore to avoid corrupting output
            if body_rows:
                commission_text = "\n\n".join(r[0] for r in body_rows)
                parliament_text = "\n\n".join(r[1] for r in body_rows)

        target = " — ".join(t for t in target_parts if t)
        # Build markdown rendering: target heading, side-by-side in two sections
        body_md_parts = []
        if target:
            body_md_parts.append(f"**Doel:** {target}")
        body_md_parts.append("## Door de Commissie voorgestelde tekst\n\n" + (commission_text or "*(geen tekst)*"))
        body_md_parts.append("## Amendement van het Europees Parlement\n\n" + (parliament_text or "*(geen tekst)*"))
        body_md = "\n\n".join(body_md_parts) + "\n"
        char_count = len(commission_text) + len(parliament_text)

        amendments.append(Amendment(num, target, commission_text, parliament_text, body_md, char_count))
        i = j

    amendments.sort(key=lambda a: a.number)
    return amendments


# =============================================================================
# Emission
# =============================================================================

def write_commission_2021(out_root: Path, scraped_at: str, articles, recitals, annexes, meta):
    files = []
    base = out_root / "history" / "commission-2021"
    for a in articles:
        rel = Path("history/commission-2021/articles") / f"article-{a.number}.md"
        reljs = rel.with_suffix(".json")
        p_md = out_root / rel; p_js = out_root / reljs
        p_md.parent.mkdir(parents=True, exist_ok=True)
        fm = {
            "language": LANGUAGE, "source_url": meta["url"], "source_celex": meta["celex"],
            "scraped_at": scraped_at,
            "version": "commission-2021",
            "article_number": str(a.number), "article_title": a.title,
            "titel_number_roman": a.titel_roman,
            "titel_number": str(a.titel_num) if a.titel_num else None,
            "titel_title": a.titel_title,
            "hoofdstuk_number": None if a.hoofdstuk_num is None else str(a.hoofdstuk_num),
            "hoofdstuk_title": a.hoofdstuk_title,
        }
        header = f"# Artikel {a.number}" + (f" — {a.title}" if a.title else "")
        md = frontmatter(fm) + f"\n{header}\n\n" + a.body_md
        p_md.write_text(md, encoding="utf-8")
        js = {**fm, "body_md": a.body_md, "body_text": a.body_text, "char_count": a.char_count}
        p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append({"kind":"article","number":a.number,
                      "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
                      "char_count":a.char_count,
                      "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()})

    for r in recitals:
        rel = Path("history/commission-2021/recitals") / f"recital-{r.number}.md"
        reljs = rel.with_suffix(".json")
        p_md = out_root / rel; p_js = out_root / reljs
        p_md.parent.mkdir(parents=True, exist_ok=True)
        fm = {"language":LANGUAGE,"source_url":meta["url"],"source_celex":meta["celex"],
              "scraped_at":scraped_at,"version":"commission-2021",
              "recital_number":str(r.number)}
        md = frontmatter(fm) + f"\n# Overweging ({r.number})\n\n" + r.body
        p_md.write_text(md, encoding="utf-8")
        js = {**fm,"body_md":r.body,"char_count":r.char_count}
        p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append({"kind":"recital","number":r.number,
                      "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
                      "char_count":r.char_count,
                      "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()})

    for x in annexes:
        rel = Path("history/commission-2021/annexes") / f"annex-{x.roman.lower()}.md"
        reljs = rel.with_suffix(".json")
        p_md = out_root / rel; p_js = out_root / reljs
        p_md.parent.mkdir(parents=True, exist_ok=True)
        fm = {"language":LANGUAGE,"source_url":meta["url"],"source_celex":meta["celex"],
              "scraped_at":scraped_at,"version":"commission-2021",
              "annex_number_roman":x.roman,"annex_number":str(x.arabic),
              "annex_title":x.title}
        md = frontmatter(fm) + f"\n# Bijlage {x.roman} — {x.title}\n\n" + x.body_md
        p_md.write_text(md, encoding="utf-8")
        js = {**fm,"body_md":x.body_md,"body_text":x.body_text,"char_count":x.char_count}
        p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append({"kind":"annex","number_roman":x.roman,"number":x.arabic,
                      "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
                      "char_count":x.char_count,
                      "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()})
    return files


def write_parliament_2023(out_root: Path, scraped_at: str, amendments, meta):
    files = []
    for a in amendments:
        rel = Path("history/parliament-2023/amendments") / f"amendment-{a.number:03d}.md"
        reljs = rel.with_suffix(".json")
        p_md = out_root / rel; p_js = out_root / reljs
        p_md.parent.mkdir(parents=True, exist_ok=True)
        fm = {"language":LANGUAGE,"source_url":meta["url"],"source_celex":meta["celex"],
              "scraped_at":scraped_at,"version":"parliament-2023",
              "amendment_number":str(a.number),"amendment_target":a.target}
        md = frontmatter(fm) + f"\n# Amendement {a.number}\n\n" + a.body_md
        p_md.write_text(md, encoding="utf-8")
        js = {**fm,"body_md":a.body_md,
              "commission_text":a.commission_text,
              "parliament_text":a.parliament_text,
              "char_count":a.char_count}
        p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append({"kind":"amendment","number":a.number,
                      "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
                      "char_count":a.char_count,
                      "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()})
    return files


# =============================================================================
# CLI
# =============================================================================

def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["commission-2021","parliament-2023"])
    p.add_argument("--html", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    html = Path(args.html)
    out  = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "_meta").mkdir(parents=True, exist_ok=True)

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = SOURCES[args.mode]

    if args.mode == "commission-2021":
        articles, recitals, annexes = parse_commission_2021(html)
        files = write_commission_2021(out, scraped_at, articles, recitals, annexes, meta)
        counts = {"articles": len(articles), "recitals": len(recitals), "annexes": len(annexes)}
    else:
        amendments = parse_parliament_2023(html)
        files = write_parliament_2023(out, scraped_at, amendments, meta)
        counts = {"amendments": len(amendments)}

    counts_path = out / "_meta" / f"counts-{args.mode}.txt"
    counts_path.write_text("\n".join(f"{k}: {v}" for k,v in counts.items()) + "\n", encoding="utf-8")

    manifest_path = out / "_meta" / f"manifest-{args.mode}.json"
    manifest = {
        "version": args.mode,
        "source_url": meta["url"], "source_celex": meta["celex"], "source_label": meta["label"],
        "language": LANGUAGE,
        "scraped_at": scraped_at,
        "source_file": str(html),
        "source_size_bytes": html.stat().st_size,
        "source_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
        "counts": counts,
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Parsed OK [{args.mode}].")
    for k,v in counts.items():
        print(f"  {k}: {v}")
    print(f"  output: {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
