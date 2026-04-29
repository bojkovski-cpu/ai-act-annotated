#!/usr/bin/env python3
"""
build_guidance.py — Step 5.2 bridge: guidance-intermediate/ → src/data + src/content.

Inputs
------
- ``guidance-intermediate/<canonical_id>/manifest.json`` for every guidance document
  ingested via 5.5a's ``ingest_guidance.py`` (and successors).
- ``guidance-intermediate/<canonical_id>/parsed/<canonical_id>_<lang>.md`` — body
  markdown per language listed in the manifest's ``languages`` field.
- ``guidance-intermediate/<canonical_id>/references/article_references_<lang>.json``
  — pin-cite list per language (only ``target_kind == 'article'`` entries are
  consumed by the reverse-index; recital / annex / other targets are ignored at
  this step).

Outputs
-------
- ``src/data/guidance.json`` — single sorted array, one entry per ``canonical_id``
  carrying the ``BilingualText`` short metadata, the per-language ``by_language``
  block verbatim from the manifest, and a ``body_paths: {en, nl}`` mapping into
  ``src/content/guidance/<lang>/<canonical_id>.md`` (entries that aren't on disk
  resolve to ``null``).
- ``src/data/guidance_index_by_article.json`` — reverse-index keyed by article
  number (string), each entry tagged with the source ``language``. Approach A
  per Decision 7 of guidance-design-note.md.
- ``src/content/guidance/<lang>/<canonical_id>.md`` — body markdown copied
  verbatim from the intermediate. ``src/content/`` is the build artefact;
  ``guidance-intermediate/`` stays the source of truth.

Schema (guidance.json entry)
----------------------------

    {
      "canonical_id": "nl_ez_aiact_guide_2025_v1_1",
      "source": "member_state",
      "document_type": "guide",
      "title": {"en": "...", "nl": "..."},
      "adoption_date": "2025-09-02",
      "entry_into_force": null,
      "end_of_validity": null,
      "endorsement_status": null,
      "supersedes": null,
      "languages": ["en", "nl"],
      "by_language": {
        "en": {page_count, paragraph_count, section_count, footnote_count,
               citations_found, source_file, source_file_checksum},
        "nl": {...}
      },
      "url": "https://..."  OR  {"en": "...", "nl": "..."},
      "body_paths": {"en": "guidance/en/<id>.md", "nl": "guidance/nl/<id>.md"},
      "editorial_note": null
    }

Schema (guidance_index_by_article.json entry)
---------------------------------------------

    {
      "5": [
        {
          "guidance_id": "<canonical_id>",
          "language": "en",
          "pin_cite": {
            "raw": "Article 5(1)(a)",
            "paragraph": "1",  // string or null (matches source target_paragraph)
            "letter": "a",     // string or null
            "subparagraph": null
          },
          "location_in_doc": {
            "section": "3.2",
            "page": 5,
            "footnote": 6
          }
        },
        ...
      ]
    }

Notes:
- ``location_in_doc`` is preserved verbatim from
  ``article_references_<lang>.json``. The 5.1 design note's schema sketch named
  ``{section, paragraph}``; the actual source carries ``{section, page, footnote}``.
  The renderer adapts. Format-validation work belongs to 4.9a, not 5.2 (per
  handoff "Known gotchas" §6).
- Pin-cite ``paragraph`` / ``letter`` / ``subparagraph`` are strings (matching
  source); the design note's TS interface declares them as ``number | string |
  null``, so the loader's type accommodates both.

Idempotency
-----------
Sorted keys, sorted arrays, deterministic ordering. Re-running on the same
inputs produces byte-identical outputs.

Asserts
-------
- Every guidance entry has ``languages`` non-empty (Pass criterion bullet 1).
- Every (canonical_id, language) pair has both a parsed body and a references
  file on disk; loud failure if either is missing.
- No two manifests share a ``canonical_id``.

Usage
-----
    python3 scripts/build_guidance.py [--repo-root PATH] [--intermediate PATH]

Defaults assume the script is run from the repo root with
``guidance-intermediate/`` one directory above (the layout established at 5.5a:
intermediate stays outside the Astro repo so source artefacts don't bloat the
deployable tree).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# ─── Paths ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT_DEFAULT = SCRIPT_DIR.parent
INTERMEDIATE_DEFAULT = REPO_ROOT_DEFAULT.parent / "guidance-intermediate"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bridge guidance-intermediate → site data.")
    p.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT_DEFAULT,
        help="Path to the Astro repo root (default: parent of scripts/).",
    )
    p.add_argument(
        "--intermediate",
        type=Path,
        default=INTERMEDIATE_DEFAULT,
        help="Path to guidance-intermediate/ (default: repo-root/../guidance-intermediate).",
    )
    return p.parse_args()


# ─── Helpers ──────────────────────────────────────────────────────────────


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    """Write JSON deterministically: sorted keys, indent=2, trailing newline, UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.write("\n")


def sort_key_pin_cite(entry: dict[str, Any]) -> tuple[Any, ...]:
    """Stable secondary sort within an article bucket."""
    loc = entry.get("location_in_doc") or {}
    return (
        entry.get("guidance_id", ""),
        entry.get("language", ""),
        str(loc.get("section", "") or ""),
        int(loc.get("page", 0) or 0),
        int(loc.get("footnote", 0) or 0),
        entry.get("pin_cite", {}).get("raw", "") or "",
    )


# ─── Per-document processing ──────────────────────────────────────────────


def process_manifest(
    manifest_path: Path,
    intermediate_root: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """
    Returns (guidance_entry, [(article_number, citation_entry), ...]).

    Side effect: copies parsed/<id>_<lang>.md → src/content/guidance/<lang>/<id>.md
    for every language in manifest.languages.
    """
    manifest = load_json(manifest_path)
    canonical_id = manifest["canonical_id"]
    languages = manifest.get("languages") or []

    if not languages:
        raise AssertionError(
            f"manifest {manifest_path} has empty 'languages' — every guidance "
            "entry must declare at least one language (Pass criterion 1)."
        )

    doc_dir = manifest_path.parent
    parsed_dir = doc_dir / "parsed"
    refs_dir = doc_dir / "references"

    body_paths: dict[str, str | None] = {"en": None, "nl": None}
    citations: list[tuple[str, dict[str, Any]]] = []

    for lang in languages:
        # 1. Validate body file exists.
        body_src = parsed_dir / f"{canonical_id}_{lang}.md"
        if not body_src.is_file():
            raise FileNotFoundError(
                f"Missing parsed body: {body_src} (declared in manifest "
                f"languages={languages}). The intermediate is incomplete."
            )

        # 2. Copy body markdown into src/content/guidance/<lang>/.
        body_dst_rel = Path("guidance") / lang / f"{canonical_id}.md"
        body_dst_abs = repo_root / "src" / "content" / body_dst_rel
        body_dst_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(body_src, body_dst_abs)
        # Path is stored relative to src/content/ for use by the loader.
        body_paths[lang] = str(body_dst_rel).replace("\\", "/")

        # 3. Validate references file exists.
        refs_path = refs_dir / f"article_references_{lang}.json"
        if not refs_path.is_file():
            raise FileNotFoundError(
                f"Missing references file: {refs_path} (manifest declares "
                f"language={lang})."
            )

        # 4. Build reverse-index entries.
        refs = load_json(refs_path)
        for ref in refs:
            if ref.get("target_kind") != "article":
                continue
            art_num = ref.get("target_article")
            if art_num is None:
                continue
            article_key = str(art_num)
            entry = {
                "guidance_id": canonical_id,
                "language": lang,
                "pin_cite": {
                    "raw": ref.get("raw_citation", "") or "",
                    "paragraph": ref.get("target_paragraph"),
                    "letter": ref.get("target_letter"),
                    "subparagraph": ref.get("target_subparagraph"),
                },
                "location_in_doc": ref.get("location_in_doc") or {},
            }
            citations.append((article_key, entry))

    # ─── Build guidance.json entry ────────────────────────────────────────

    guidance_entry: dict[str, Any] = {
        "canonical_id": canonical_id,
        "source": manifest.get("source"),
        "document_type": manifest.get("document_type"),
        "title": manifest.get("title") or {},
        "adoption_date": manifest.get("adoption_date"),
        "entry_into_force": manifest.get("entry_into_force"),
        "end_of_validity": manifest.get("end_of_validity"),
        "endorsement_status": manifest.get("endorsement_status"),
        "supersedes": manifest.get("supersedes"),
        "languages": list(languages),
        "by_language": manifest.get("by_language") or {},
        "url": manifest.get("url"),
        "body_paths": body_paths,
        "editorial_note": manifest.get("editorial_note"),
    }

    return guidance_entry, citations


# ─── Main ─────────────────────────────────────────────────────────────────


def main() -> int:
    args = parse_args()
    repo_root: Path = args.repo_root
    intermediate: Path = args.intermediate

    if not intermediate.is_dir():
        print(
            f"ERROR: guidance-intermediate not found at {intermediate}",
            file=sys.stderr,
        )
        return 2

    manifests = sorted(intermediate.glob("*/manifest.json"))
    if not manifests:
        print(
            f"WARNING: no guidance manifests found under {intermediate}. "
            "Writing empty outputs.",
            file=sys.stderr,
        )

    # Clear stale src/content/guidance/ entries — only the canonical_ids we
    # see this run should remain. Idempotent: same inputs → same files.
    content_root = repo_root / "src" / "content" / "guidance"
    if content_root.exists():
        shutil.rmtree(content_root)

    seen_ids: set[str] = set()
    guidance_entries: list[dict[str, Any]] = []
    reverse_index: dict[str, list[dict[str, Any]]] = {}

    for manifest_path in manifests:
        entry, citations = process_manifest(manifest_path, intermediate, repo_root)
        cid = entry["canonical_id"]
        if cid in seen_ids:
            raise ValueError(
                f"Duplicate canonical_id '{cid}' across manifests — every "
                "guidance document must declare a unique slug."
            )
        seen_ids.add(cid)
        guidance_entries.append(entry)

        for article_key, citation in citations:
            reverse_index.setdefault(article_key, []).append(citation)

    # ─── Sort guidance.json: adoption_date DESC, tie-break canonical_id ASC ─
    guidance_entries.sort(
        key=lambda e: (
            # Reversed for desc sort via negation-style trick: use a tuple where
            # first element sorts as (large_string_first). Easier: sort ASC, then
            # reverse, then secondary-sort by canonical_id ASC. Two-pass:
            e.get("adoption_date") or "",
            e.get("canonical_id") or "",
        )
    )
    # Re-sort: adoption_date desc, canonical_id asc.
    guidance_entries.sort(
        key=lambda e: (
            -_date_to_int(e.get("adoption_date")),
            e.get("canonical_id") or "",
        )
    )

    # ─── Sort reverse-index entries within each article bucket ────────────
    for article_key in list(reverse_index.keys()):
        reverse_index[article_key] = sorted(
            reverse_index[article_key], key=sort_key_pin_cite
        )

    # ─── Sort top-level keys numerically (article numbers as strings) ─────
    sorted_index = {
        k: reverse_index[k]
        for k in sorted(reverse_index.keys(), key=lambda x: (int(x) if x.isdigit() else 9999, x))
    }

    # ─── Write outputs ────────────────────────────────────────────────────
    data_root = repo_root / "src" / "data"
    write_json(data_root / "guidance.json", guidance_entries)
    write_json(data_root / "guidance_index_by_article.json", sorted_index)

    # ─── Report ───────────────────────────────────────────────────────────
    total_citations = sum(len(v) for v in sorted_index.values())
    by_lang_counts: dict[str, int] = {}
    for entries in sorted_index.values():
        for e in entries:
            by_lang_counts[e["language"]] = by_lang_counts.get(e["language"], 0) + 1

    top_articles = sorted(
        sorted_index.items(), key=lambda kv: -len(kv[1])
    )[:5]

    print(f"build_guidance: {len(guidance_entries)} document(s) processed.")
    for e in guidance_entries:
        body_count = sum(1 for v in e["body_paths"].values() if v)
        print(
            f"  · {e['canonical_id']}  [{','.join(e['languages'])}]  "
            f"body files: {body_count}"
        )
    print(
        f"build_guidance: {total_citations} reverse-index entries across "
        f"{len(sorted_index)} articles."
    )
    if by_lang_counts:
        print("  · per language: " + ", ".join(
            f"{k}={v}" for k, v in sorted(by_lang_counts.items())
        ))
    if top_articles:
        print("  · top 5 articles by citation count: " + ", ".join(
            f"art {k} ({len(v)})" for k, v in top_articles
        ))
    print(f"build_guidance: outputs written under {data_root}.")
    return 0


def _date_to_int(d: Any) -> int:
    """ISO date 'YYYY-MM-DD' → integer for desc sort. None / missing → 0."""
    if not d or not isinstance(d, str):
        return 0
    try:
        return int(d.replace("-", ""))
    except ValueError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
