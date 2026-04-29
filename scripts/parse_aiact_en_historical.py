"""
parse_aiact_en_historical.py — Step 4.3c parser for the EN Parliament-2023 amendments.

Mirrors parse_aiact_nl_historical.py (NL precedent from Step 4.3a). Separate file
per Pavle's call (Step 4.3c, 2026-04-28) — clean git history, no parametric
branching. EUR-Lex serves the same HTML template across language editions of a
CELEX, so the parser logic is identical to NL aside from:

  - Language-specific column-header strings ("Text proposed by the Commission" /
    "Amendment" instead of "Door de Commissie voorgestelde tekst" / "Amendement").
  - Markdown section headings ("Text proposed by the Commission" /
    "Amendment of the European Parliament").
  - Empty-cell placeholder ("*(no text)*" instead of "*(geen tekst)*").
  - The amendment anchor matches "Amendment N" instead of "Amendement N".

Scope: parliament-2023 only. EN commission-2021 has a smaller gap (1 article,
19 recitals) and was explicitly out of scope for this step.

char_count semantics: per Step 4.3c handoff, char_count = len(parliament_text)
only (NL existing data uses len(commission)+len(parliament) — a known divergence,
flagged in the completion notes).

Filename convention: amendment-NNN.{json,md} with 3-digit padding.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

LANGUAGE = "en"

SOURCES = {
    "parliament-2023": {
        "celex": "52023AP0236",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52023AP0236",
        "label": "European Parliament position (14 June 2023) — P9_TA(2023)0236",
    },
}

NBSP = re.compile(" ")
MULTI = re.compile(r"[ \t]{2,}")


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
# Parliament 2023 — amendments (EN)
# =============================================================================

@dataclass
class Amendment:
    number: int
    target: str           # e.g. "Proposal for a regulation — Recital 1"
    commission_text: str  # left column — Commission's original
    parliament_text: str  # right column — Parliament's amendment
    body_md: str
    char_count: int


def parse_parliament_2023(html_path: Path):
    """Walk grseq-1 'Amendment N' markers, collect the next 1-3 grseq-1 paragraphs as the
    target heading, then the next <table> (the Commission-vs-Parliament comparison)."""
    with html_path.open(encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    grs = soup.find_all(class_="oj-ti-grseq-1")
    amendments: list[Amendment] = []
    i = 0
    while i < len(grs):
        g = grs[i]
        txt = ptext(g)
        m = re.match(r"^Amendment\s+(\d+)$", txt)
        if not m:
            i += 1
            continue
        num = int(m.group(1))
        # Collect target paragraphs (e.g. "Proposal for a regulation" + "Recital 1")
        # until the next "Amendment N" anchor or 4 paragraphs collected.
        target_parts = []
        j = i + 1
        while j < len(grs):
            t = ptext(grs[j])
            if re.match(r"^Amendment\s+\d+$", t):
                break
            target_parts.append(t)
            j += 1
            if len(target_parts) >= 4:
                break

        # Find the next <table> after g but before the next Amendment anchor.
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
            rows = table.find_all("tr")
            body_rows = []
            for tr in rows:
                cells = tr.find_all(["td","th"], recursive=False)
                if not cells:
                    cells = tr.find_all(["td","th"])
                texts = [ptext(c) for c in cells]
                # Skip the column-header row.
                joined = " | ".join(texts).lower().strip()
                if ("text proposed by the commission" in joined
                        or joined in ("amendment", "| amendment", "amendment |",
                                      "text proposed by the commission | amendment")):
                    continue
                # Skip fully-empty rows.
                if not any(texts):
                    continue
                if len(texts) == 2:
                    # Preserve empty cells — a "(new)" amendment has an empty Commission column
                    # and must NOT be duplicated into both sides.
                    body_rows.append([texts[0], texts[1]])
                elif len(texts) == 1:
                    # Truly single-cell row (e.g. spanned heading). Mirror to both sides.
                    body_rows.append([texts[0], texts[0]])
                # rows with >2 cells are rare and ambiguous — ignore
            if body_rows:
                commission_text = "\n\n".join(r[0] for r in body_rows)
                parliament_text = "\n\n".join(r[1] for r in body_rows)

        target = " — ".join(t for t in target_parts if t)
        body_md_parts = []
        if target:
            body_md_parts.append(f"**Target:** {target}")
        body_md_parts.append("## Text proposed by the Commission\n\n" + (commission_text or "*(no text)*"))
        body_md_parts.append("## Amendment of the European Parliament\n\n" + (parliament_text or "*(no text)*"))
        body_md = "\n\n".join(body_md_parts) + "\n"

        # char_count: per 4.3c handoff, on parliament_text only (NL uses sum — divergence noted).
        char_count = len(parliament_text)

        amendments.append(Amendment(num, target, commission_text, parliament_text, body_md, char_count))
        i = j

    amendments.sort(key=lambda a: a.number)
    return amendments


# =============================================================================
# Emission
# =============================================================================

def write_parliament_2023(out_root: Path, scraped_at: str, amendments, meta):
    files = []
    for a in amendments:
        rel = Path("history/parliament-2023/amendments") / f"amendment-{a.number:03d}.md"
        reljs = rel.with_suffix(".json")
        p_md = out_root / rel; p_js = out_root / reljs
        p_md.parent.mkdir(parents=True, exist_ok=True)
        fm = {
            "language": LANGUAGE,
            "source_url": meta["url"],
            "source_celex": meta["celex"],
            "scraped_at": scraped_at,
            "version": "parliament-2023",
            "amendment_number": str(a.number),
            "amendment_target": a.target,
        }
        md = frontmatter(fm) + f"\n# Amendment {a.number}\n\n" + a.body_md
        p_md.write_text(md, encoding="utf-8")
        js = {
            **fm,
            "body_md": a.body_md,
            "commission_text": a.commission_text,
            "parliament_text": a.parliament_text,
            "char_count": a.char_count,
        }
        p_js.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append({
            "kind": "amendment",
            "number": a.number,
            "md_path": str(rel).replace("\\", "/"),
            "json_path": str(reljs).replace("\\", "/"),
            "char_count": a.char_count,
            "sha256_md": hashlib.sha256(md.encode("utf-8")).hexdigest(),
        })
    return files


# =============================================================================
# CLI
# =============================================================================

def main(argv):
    p = argparse.ArgumentParser(description="Parse EN AI Act Parliament-2023 amendments.")
    p.add_argument("--mode", default="parliament-2023",
                   choices=["parliament-2023"],
                   help="Only parliament-2023 is supported in 4.3c.")
    p.add_argument("--html", required=True, help="Path to the cached EN EUR-Lex HTML.")
    p.add_argument("--out", required=True, help="Output root (e.g. english-intermediate/).")
    # Fixed scrape timestamp lets us run idempotently without timestamp drift.
    p.add_argument("--scraped-at", default=None,
                   help="ISO timestamp to embed (default: file mtime in UTC).")
    args = p.parse_args(argv)

    html = Path(args.html)
    if not html.exists():
        print(f"ERROR: source HTML not found: {html}", file=sys.stderr)
        return 2
    out  = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "_meta").mkdir(parents=True, exist_ok=True)

    if args.scraped_at:
        scraped_at = args.scraped_at
    else:
        # Use the source HTML's mtime (UTC) so re-runs are byte-identical.
        mtime = datetime.fromtimestamp(html.stat().st_mtime, tz=timezone.utc)
        scraped_at = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = SOURCES[args.mode]

    amendments = parse_parliament_2023(html)
    files = write_parliament_2023(out, scraped_at, amendments, meta)
    counts = {"amendments": len(amendments)}

    # Hard assertion — the EN edition of CELEX 52023AP0236 must have 771 amendments,
    # mirroring NL. If this fails, the parser is broken.
    expected = 771
    assert counts["amendments"] == expected, \
        f"Expected {expected} amendments, got {counts['amendments']}"

    counts_path = out / "_meta" / f"counts-{args.mode}.txt"
    counts_path.write_text("\n".join(f"{k}: {v}" for k,v in counts.items()) + "\n",
                           encoding="utf-8")

    manifest_path = out / "_meta" / f"manifest-{args.mode}.json"
    manifest = {
        "version": args.mode,
        "source_url": meta["url"],
        "source_celex": meta["celex"],
        "source_label": meta["label"],
        "language": LANGUAGE,
        "scraped_at": scraped_at,
        "source_file": str(html),
        "source_size_bytes": html.stat().st_size,
        "source_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
        "counts": counts,
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    print(f"Parsed OK [{args.mode}].")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"  output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
