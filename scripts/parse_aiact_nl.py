"""
parse_aiact_nl.py — Step 4.3a parser (Dutch final adopted, CELEX 32024R1689).

Reads EUR-Lex Dutch HTML, emits .md + .json for each article / recital / annex,
plus _meta/manifest.json and _meta/counts.txt.

Filename conventions match the existing English corpus:
- articles/chapter-NN/article-NN.md   (2-digit chapter; article min-2-digit, natural width)
- recitals/recital-NNN.md             (3-digit)
- annexes/annex-<roman>.md
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

SOURCE_CELEX = "32024R1689"
SOURCE_URL   = "https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=OJ:L_202401689"
LANGUAGE     = "nl"

ROMAN = {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9,
         "X":10,"XI":11,"XII":12,"XIII":13}

NBSP_RE      = re.compile("\u00a0")
MULTI_WS_RE  = re.compile(r"[ \t]{2,}")
NUM_LEAD_RE  = re.compile(r"^(\d+)\.\s+")


def clean(t: str) -> str:
    t = NBSP_RE.sub(" ", t or "")
    t = MULTI_WS_RE.sub(" ", t)
    return t.strip()


def ptext(p) -> str:
    return clean(p.get_text(" ", strip=True)) if p is not None else ""


def yaml_escape(s: str) -> str:
    if s is None:
        return '""'
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


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


# --- Markdown conversion ----------------------------------------------------

def _top_level_rows(table: Tag) -> list:
    """Rows belonging to this table only — skip rows inside nested tables.

    HTML parsers inject <tbody>, so the true row path is table > tbody > tr.
    Fallback to direct <tr> children for the rare untemplated case.
    """
    rows = []
    for tb in table.find_all("tbody", recursive=False):
        rows.extend(tb.find_all("tr", recursive=False))
    rows.extend(table.find_all("tr", recursive=False))
    return rows


def _list_from_table(table: Tag) -> list:
    lines = []
    for tr in _top_level_rows(table):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 2:
            continue
        marker = clean(tds[0].get_text(" ", strip=True))
        body   = _cell_md(tds[1])
        if not marker:
            if body:
                lines.append(body)
            continue
        first, *rest = body.split("\n") if body else [""]
        lines.append(f"- {marker} {first}".rstrip())
        for line in rest:
            lines.append(f"  {line}" if line else "")
    return lines


def _cell_md(cell: Tag) -> str:
    parts = []
    for child in cell.children:
        if isinstance(child, NavigableString):
            s = clean(str(child))
            if s:
                parts.append(s)
        elif isinstance(child, Tag):
            if child.name == "p":
                t = clean(child.get_text(" ", strip=True))
                if t:
                    parts.append(t)
            elif child.name == "table":
                parts.extend(_list_from_table(child))
            elif child.name == "div":
                parts.append(_cell_md(child))
    return "\n".join(p for p in parts if p != "")


def body_md(container: Tag, skip=()) -> str:
    skip_ids = {id(s) for s in skip}
    out = []

    def walk(node: Tag):
        if id(node) in skip_ids:
            return
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            if id(child) in skip_ids:
                continue
            cls = child.get("class") or []
            if child.name == "p":
                t = clean(child.get_text(" ", strip=True))
                if not t:
                    continue
                if "oj-ti-grseq-1" in cls:
                    out.append(f"### {t}")
                elif any(c in cls for c in ("oj-ti-art","oj-sti-art","oj-ti-section-1","oj-ti-section-2","oj-doc-ti")):
                    # Headings handled by caller
                    continue
                else:
                    m = NUM_LEAD_RE.match(t)
                    if m:
                        t = f"**{m.group(1)}.** {t[m.end():]}"
                    out.append(t)
            elif child.name == "table":
                out.extend(_list_from_table(child))
            elif child.name == "div":
                walk(child)

    walk(container)
    return ("\n\n".join(p for p in out if p) ).strip() + "\n"


# --- Dataclasses ------------------------------------------------------------

@dataclass
class Article:
    number: int; title: str
    chapter_roman: str; chapter_num: int; chapter_title: str
    section_num: int | None; section_title: str | None
    body: str; body_text: str; char_count: int; anchor: str

@dataclass
class Recital:
    number: int; body: str; char_count: int; anchor: str

@dataclass
class Annex:
    roman: str; arabic: int; title: str; body: str; char_count: int; anchor: str


# --- Parsing ----------------------------------------------------------------

def chapter_for(art_div: Tag):
    """Return (roman, arabic, title) for the nearest HOOFDSTUK ancestor (in document order)."""
    for prev in art_div.find_all_previous("p", class_="oj-ti-section-1"):
        t = ptext(prev)
        if t.startswith("HOOFDSTUK"):
            m = re.match(r"^HOOFDSTUK\s+([IVX]+)$", t)
            roman = m.group(1) if m else ""
            arabic = ROMAN.get(roman, 0)
            title_p = prev.find_next("p", class_="oj-ti-section-2")
            return roman, arabic, ptext(title_p)
    return "", 0, ""


def section_for(art_div: Tag):
    """Return (num, title) if the article sits inside an AFDELING; otherwise (None, None)."""
    for prev in art_div.find_all_previous("p", class_="oj-ti-section-1"):
        t = ptext(prev)
        if t.startswith("AFDELING"):
            m = re.match(r"^AFDELING\s+(\d+)$", t)
            if not m:
                return None, None
            num = int(m.group(1))
            title_p = prev.find_next("p", class_="oj-ti-section-2")
            return num, ptext(title_p)
        if t.startswith("HOOFDSTUK"):
            return None, None
    return None, None


def annex_region_siblings(ti: Tag) -> list:
    """All element siblings from `ti` up to the next BIJLAGE or oj-final/oj-doc-end."""
    out = []
    node = ti
    while node is not None:
        if isinstance(node, Tag):
            cls = node.get("class") or []
            if node is not ti and "oj-doc-ti" in cls and ptext(node).startswith("BIJLAGE"):
                break
            if "oj-final" in cls or "oj-doc-end" in cls or "oj-signatory" in cls:
                break
            out.append(node)
        node = node.next_sibling
    return out


def parse(html_path: Path):
    with html_path.open("r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Articles
    articles = []
    for art in soup.select("div.eli-subdivision[id^=art_]"):
        m = re.fullmatch(r"art_(\d+)", art.get("id", ""))
        if not m:
            continue
        num = int(m.group(1))
        ti_art = art.find("p", class_="oj-ti-art", recursive=False)
        title_wrap = art.find("div", class_="eli-title", recursive=False)
        sti = art.select_one(".oj-sti-art")
        title = ptext(sti)
        c_roman, c_num, c_title = chapter_for(art)
        s_num, s_title = section_for(art)
        skip = [x for x in (ti_art, title_wrap) if x is not None]
        bmd = body_md(art, skip=skip)
        btext = clean(art.get_text(" ", strip=True))
        articles.append(Article(num, title, c_roman, c_num, c_title, s_num, s_title, bmd, btext, len(btext), art.get("id")))
    articles.sort(key=lambda a: a.number)

    # Recitals
    recitals = []
    for rct in soup.select("div.eli-subdivision[id^=rct_]"):
        m = re.fullmatch(r"rct_(\d+)", rct.get("id", ""))
        if not m:
            continue
        num = int(m.group(1))
        body = ""
        table = rct.find("table")
        if table is not None:
            rows = _top_level_rows(table)
            if rows:
                tds = rows[0].find_all("td", recursive=False)
                if len(tds) >= 2:
                    body = ptext(tds[1])
        if not body:
            body = ptext(rct)
        recitals.append(Recital(num, body + "\n", len(body), rct.get("id")))
    recitals.sort(key=lambda r: r.number)

    # Annexes
    annexes = []
    for ti in soup.select("p.oj-doc-ti"):
        heading = ptext(ti)
        m = re.match(r"^BIJLAGE\s+([IVX]+)$", heading)
        if not m:
            continue
        roman = m.group(1)
        arabic = ROMAN.get(roman)
        if not arabic:
            continue
        sibs = annex_region_siblings(ti)
        title = ""
        # look for a second oj-doc-ti (the annex subtitle) inside the region
        for sib in sibs[1:]:
            if isinstance(sib, Tag):
                sub = sib if (sib.name == "p" and "oj-doc-ti" in (sib.get("class") or [])) else sib.select_one("p.oj-doc-ti") if hasattr(sib, 'select_one') else None
                if sub is not None:
                    title = ptext(sub)
                    break
        # body: concatenate body_md of each sibling (skipping ti itself)
        parts = []
        for sib in sibs:
            if sib is ti:
                continue
            if not isinstance(sib, Tag):
                continue
            if sib.name == "p":
                t = ptext(sib)
                if not t:
                    continue
                cls = sib.get("class") or []
                if "oj-doc-ti" in cls:
                    parts.append(f"## {t}")
                elif "oj-ti-grseq-1" in cls:
                    parts.append(f"### {t}")
                elif any(c in cls for c in ("oj-ti-section-1","oj-ti-section-2")):
                    parts.append(f"### {t}")
                else:
                    m2 = NUM_LEAD_RE.match(t)
                    if m2:
                        t = f"**{m2.group(1)}.** {t[m2.end():]}"
                    parts.append(t)
            elif sib.name == "table":
                parts.extend(_list_from_table(sib))
            elif sib.name == "div":
                parts.append(body_md(sib))
        bmd = "\n\n".join(p for p in parts if p).strip() + "\n"
        btext = "\n\n".join(clean(s.get_text(" ", strip=True)) for s in sibs if isinstance(s, Tag) and s is not ti).strip()
        annexes.append(Annex(roman, arabic, title, bmd, len(btext), ti.get("id") or f"bijlage_{roman}"))
    annexes.sort(key=lambda a: a.arabic)

    return articles, recitals, annexes


# --- File emission ----------------------------------------------------------

def article_name(n: int) -> str:
    return f"article-{n:02d}" if n < 100 else f"article-{n}"

def recital_name(n: int) -> str:
    return f"recital-{n:03d}"

def annex_name(r: str) -> str:
    return f"annex-{r.lower()}"

def chapter_dir(c: int) -> str:
    return f"chapter-{c:02d}"


def write_article(a: Article, root: Path, scraped_at: str) -> dict:
    rel = Path("regulation/articles") / chapter_dir(a.chapter_num) / (article_name(a.number) + ".md")
    reljs = rel.with_suffix(".json")
    p_md = root / rel
    p_js = root / reljs
    p_md.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "language": LANGUAGE, "source_url": SOURCE_URL, "source_celex": SOURCE_CELEX,
        "scraped_at": scraped_at,
        "article_number": str(a.number), "article_title": a.title,
        "chapter_number": str(a.chapter_num), "chapter_number_roman": a.chapter_roman,
        "chapter_title": a.chapter_title,
        "section_number": None if a.section_num is None else str(a.section_num),
        "section_title": a.section_title,
        "anchor": a.anchor,
    }
    md = frontmatter(fm) + f"\n# Artikel {a.number} — {a.title}\n\n" + a.body
    p_md.write_text(md, encoding="utf-8")
    js = {**fm, "body_md": a.body, "body_text": a.body_text, "char_count": a.char_count}
    p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"kind":"article","number":a.number,
            "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
            "char_count":a.char_count,
            "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()}


def write_recital(r: Recital, root: Path, scraped_at: str) -> dict:
    rel = Path("regulation/recitals") / (recital_name(r.number) + ".md")
    reljs = rel.with_suffix(".json")
    p_md = root / rel; p_js = root / reljs
    p_md.parent.mkdir(parents=True, exist_ok=True)
    fm = {"language":LANGUAGE,"source_url":SOURCE_URL,"source_celex":SOURCE_CELEX,
          "scraped_at":scraped_at,"recital_number":str(r.number),"anchor":r.anchor}
    md = frontmatter(fm) + f"\n# Overweging ({r.number})\n\n" + r.body
    p_md.write_text(md, encoding="utf-8")
    js = {**fm,"body_md":r.body,"char_count":r.char_count}
    p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"kind":"recital","number":r.number,
            "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
            "char_count":r.char_count,
            "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()}


def write_annex(x: Annex, root: Path, scraped_at: str) -> dict:
    rel = Path("regulation/annexes") / (annex_name(x.roman) + ".md")
    reljs = rel.with_suffix(".json")
    p_md = root / rel; p_js = root / reljs
    p_md.parent.mkdir(parents=True, exist_ok=True)
    fm = {"language":LANGUAGE,"source_url":SOURCE_URL,"source_celex":SOURCE_CELEX,
          "scraped_at":scraped_at,"annex_number_roman":x.roman,"annex_number":str(x.arabic),
          "annex_title":x.title,"anchor":x.anchor}
    md = frontmatter(fm) + f"\n# Bijlage {x.roman} — {x.title}\n\n" + x.body
    p_md.write_text(md, encoding="utf-8")
    js = {**fm,"body_md":x.body,"char_count":x.char_count}
    p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"kind":"annex","number_roman":x.roman,"number":x.arabic,
            "md_path":str(rel).replace("\\","/"),"json_path":str(reljs).replace("\\","/"),
            "char_count":x.char_count,
            "sha256_md":hashlib.sha256(md.encode("utf-8")).hexdigest()}


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--html", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    html_path = Path(args.html)
    out_root  = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "_meta").mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    articles, recitals, annexes = parse(html_path)
    files = []
    for a in articles: files.append(write_article(a, out_root, scraped_at))
    for r in recitals: files.append(write_recital(r, out_root, scraped_at))
    for x in annexes:  files.append(write_annex(x, out_root, scraped_at))

    counts = [f"articles: {len(articles)}",
              f"recitals: {len(recitals)}",
              f"annexes:  {len(annexes)}"]
    (out_root / "_meta" / "counts.txt").write_text("\n".join(counts)+"\n", encoding="utf-8")

    manifest = {
        "source_url": SOURCE_URL, "source_celex": SOURCE_CELEX, "language": LANGUAGE,
        "scraped_at": scraped_at, "source_file": str(html_path),
        "source_size_bytes": html_path.stat().st_size,
        "source_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        "counts": {"articles": len(articles), "recitals": len(recitals), "annexes": len(annexes)},
        "files": files,
    }
    (out_root / "_meta" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Parsed OK.")
    for line in counts: print("  " + line)
    print(f"  output: {out_root}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
