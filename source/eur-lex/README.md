# EUR-Lex source HTML preservation

This folder is the **canonical local cache** of EUR-Lex source HTML for the
AI Act (Regulation (EU) 2024/1689, CELEX 32024R1689) in EN and NL.

## Why this folder exists

`articles_en.json` is downstream of `ai_act_structured.json`, which is itself
downstream of EUR-Lex HTML processed by a parser that does not currently exist
in this repo. If EUR-Lex ships a corrigendum (or the upstream JSON is damaged),
the parse must be reconstructed (handoff Layer 2 Item 2.1). That reconstruction
needs the source HTML; this folder is where it lives.

## Filename convention

`<fetch-date>_<eur-lex-filename>`

Where `<eur-lex-filename>` is the canonical filename EUR-Lex itself emits (the
OJ-reference form `L_202401689EN.000101.fmx.xml.html` for the AI Act EN, etc.).
This preserves the upstream provenance verbatim.

Examples:

- `2026-05-19_L_202401689EN.000101.fmx.xml.html` — AI Act EN base text, fetched 2026-05-19
- `2026-05-19_L_202401689NL.000101.fmx.xml.html` — AI Act NL base text, fetched 2026-05-19

For corrigenda, EUR-Lex emits a different OJ reference (e.g. R(02) is
`L_202591038`). The corrigendum HTML lands as a new file under its own OJ ref:

- `<date>_L_202591038NL.000101.fmx.xml.html` — R(02) NL, when fetched

## Update policy

**Do not overwrite.** Each fetch lands as a new file with that day's date prefix.
This preserves the audit trail: what was the canonical text on the day we
ingested it. If EUR-Lex publishes a corrigendum that materially changes the
text, fetch the corrected version with that day's date as a new file; the
previous fetch stays for diff / audit.

## How to populate

EUR-Lex's HTML rendering is a JavaScript-rendered single-page app. Direct
fetches via `curl`, `Invoke-WebRequest`, or `mcp__workspace__web_fetch` all
return the empty SPA shell — they will look like they succeeded but the saved
file will be 0 bytes (verified 2026-05-19).

**Use one of these instead:**

### Option A — Browser save (30 seconds, no setup)

1. Open the URL in Chrome, Firefox, or Edge.
2. `Ctrl+S` → save as "Webpage, HTML Only".
3. Rename to match the filename convention above (prepend the fetch date).
4. Place in this folder.
5. Commit + push.

Source URLs for the base regulation:

- EN: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689
- NL: https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32024R1689

### Option B — Claude in Chrome

Spawn a Claude-in-Chrome session, ask it to fetch the URLs above and save
them to this folder with the date-prefixed filename convention.

### Option C — Parallel PDF archive (recommended alongside the HTML)

PDFs ARE fetchable via `Invoke-WebRequest -UseBasicParsing`. They serve as a
canonical archival form even if the HTML re-parse later needs a different
intermediate format:

```powershell
cd 'C:\CoWork\AI Act\ai-act-annotated'
$date = Get-Date -Format "yyyy-MM-dd"
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
Invoke-WebRequest -Uri "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689" `
  -UserAgent $ua -UseBasicParsing -OutFile "source\eur-lex\${date}_L_202401689EN.pdf"
Invoke-WebRequest -Uri "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32024R1689" `
  -UserAgent $ua -UseBasicParsing -OutFile "source\eur-lex\${date}_L_202401689NL.pdf"
git add source/eur-lex/*.pdf
git commit -m "source: parallel PDF archive of CELEX 32024R1689 (fetched $date)"
```

## Cross-references

- Risk catalogue: `control-room/reference/functional-spec-aiact-asbuilt-roadmap-2026-05-18.md` §A.12
- Layer 1 Item 1.3 (parent ingestion handoff): closes when both EN and NL HTML are committed
- Layer 2 Item 2.1 (parser reconstruction): consumes whatever lands here
- Corrigenda re-ingest: see `control-room/deployment/step-6.8-r02-nl-reingest-handoff.md`

## Corrigenda known as of 2026-05-18 (per parent control-room inventory)

- `32024R1689R(01)` — 9 October 2025 (OJ L, 2025/90802). Languages: ES / DE / FR / GA / LT / HU / SK / SL / SV (per parent's WebSearch summary — `Verify` direct EUR-Lex AUTO endpoint for EN status).
- `32024R1689R(02)` — 19 December 2025 (OJ L, 2025/91038). Languages: NL + SL only. **Affects this site's NL text.**

## Provenance note (2026-05-19)

First population came via browser "Save Page As" from Pavle's session. Files
upload-staged at `C:\Users\ReMarkt\AppData\Roaming\Claude\...\uploads\`,
copied into this folder by the AI Act control-room chat, then committed.

Direct fetch tooling tested and failed:
- `curl` from Cowork sandbox — proxy 403
- `mcp__workspace__web_fetch` — empty body
- PowerShell `Invoke-WebRequest` with `-UseBasicParsing` and real-browser UA — wrote 0-byte files (SPA shell behavior)

Browser save is the reliable path. PDF fetch via IWR works as the parallel archive.
