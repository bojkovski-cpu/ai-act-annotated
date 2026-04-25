# AI Act — Dutch intermediate (step 4.3a)

This folder is the **output** of `scripts/parse_aiact_nl.py` run against the Dutch
EUR-Lex HTML of Regulation (EU) 2024/1689 (CELEX `32024R1689`).

It is **generated**, not hand-edited. Regenerate with:

```powershell
python scripts\parse_aiact_nl.py `
  --html "path\to\AI Act NL.html" `
  --out  dutch-intermediate
```

## Scope (2026-04-24)

- Covers only the **final adopted text** (final-2024). Commission 2021 and
  Parliament 2023 Dutch versions are not yet ingested — step 4.3a remains
  formally `in_progress` until those three sources are complete.
- Format: both `.md` (frontmatter + body) and `.json` per article / recital / annex.
- Filename conventions mirror the existing English corpus at `docs/`.

## Layout

```
regulation/
  articles/chapter-NN/article-NN.md    # 2-digit chapter; article min-2-digit natural-width
  articles/chapter-NN/article-NN.json
  recitals/recital-NNN.md              # 3-digit
  recitals/recital-NNN.json
  annexes/annex-<roman>.md
  annexes/annex-<roman>.json
_meta/
  manifest.json
  counts.txt
```

## Do not

- Do not let an Astro/MkDocs build include `dutch-intermediate/`. The folder
  has a `.gitignore` that excludes everything; adjust the build glob if needed.
- Do not run the English `integrate_self_contained_history.py` against this —
  cross-reference integration is step 4.3b, not 4.3a.
