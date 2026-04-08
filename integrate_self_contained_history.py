#!/usr/bin/env python3
"""
Self-Contained Drafting History Integration Script

Integrates historical AI Act versions into the existing MkDocs site by:
1. Adding internal cross-references to historical version files
2. Adding "Drafting History" collapsible sections to current articles/recitals
3. Creating version index pages
"""

import argparse
import os
import re
import glob
from pathlib import Path


VERSIONS = {
    "commission-2021": {
        "name": "Commission Proposal (April 2021)",
        "short": "Commission 2021",
        "date": "April 2021",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52021PC0206",
        "description": "Initial proposal by the European Commission",
    },
    "parliament-2023": {
        "name": "Parliament Position (June 2023)",
        "short": "Parliament 2023",
        "date": "June 2023",
        "source_url": "https://www.europarl.europa.eu/doceo/document/TA-9-2023-0236_EN.html",
        "description": "European Parliament negotiating position",
    },
    "final-2024": {
        "name": "Final Adopted Text (June 2024)",
        "short": "Final 2024",
        "date": "June 2024",
        "source_url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
        "description": "Official regulation as published in the Official Journal",
    },
}


def find_current_article(docs_dir, article_num):
    """Find the current article file given an article number."""
    padded = f"article-{int(article_num):02d}.md"
    matches = glob.glob(os.path.join(docs_dir, "articles", "chapter-*", padded))
    if matches:
        return matches[0]
    return None


def find_current_recital(docs_dir, recital_num):
    """Find the current recital file given a recital number."""
    padded = f"recital-{int(recital_num):03d}.md"
    path = os.path.join(docs_dir, "recitals", padded)
    if os.path.exists(path):
        return path
    return None


def extract_number(filename):
    """Extract the number from a filename like article-5.md or recital-12.md."""
    m = re.search(r'(?:article|recital)-(\d+)\.md$', filename)
    if m:
        return int(m.group(1))
    return None


def scan_versions(docs_dir):
    """Scan all historical versions and return their contents."""
    history_dir = os.path.join(docs_dir, "history")
    results = {}

    for version_key, version_info in VERSIONS.items():
        version_dir = os.path.join(history_dir, version_key)
        if not os.path.isdir(version_dir):
            continue

        articles_dir = os.path.join(version_dir, "articles")
        recitals_dir = os.path.join(version_dir, "recitals")

        article_files = sorted(glob.glob(os.path.join(articles_dir, "article-*.md"))) if os.path.isdir(articles_dir) else []
        recital_files = sorted(glob.glob(os.path.join(recitals_dir, "recital-*.md"))) if os.path.isdir(recitals_dir) else []

        results[version_key] = {
            "articles": article_files,
            "recitals": recital_files,
            "article_nums": sorted([extract_number(os.path.basename(f)) for f in article_files if extract_number(os.path.basename(f)) is not None]),
            "recital_nums": sorted([extract_number(os.path.basename(f)) for f in recital_files if extract_number(os.path.basename(f)) is not None]),
        }

    return results


def compute_relative_path(from_file, to_file):
    """Compute relative path from one file to another."""
    from_dir = os.path.dirname(os.path.abspath(from_file))
    to_abs = os.path.abspath(to_file)
    return os.path.relpath(to_abs, from_dir)


def add_cross_references_to_historical(docs_dir, version_data):
    """Add internal cross-references to historical version files."""
    history_dir = os.path.join(docs_dir, "history")
    updated = 0

    for version_key in VERSIONS:
        if version_key not in version_data:
            continue

        data = version_data[version_key]

        # Process articles
        for article_file in data["articles"]:
            num = extract_number(os.path.basename(article_file))
            if num is None:
                continue

            cross_refs = build_cross_references_for_historical(
                article_file, "article", num, version_key, version_data, docs_dir
            )

            if cross_refs:
                content = Path(article_file).read_text(encoding="utf-8")
                # Insert cross-references before the --- metadata footer
                if "\n---\n" in content:
                    parts = content.rsplit("\n---\n", 1)
                    new_content = parts[0] + "\n\n" + cross_refs + "\n\n---\n" + parts[1]
                else:
                    new_content = content + "\n\n" + cross_refs
                Path(article_file).write_text(new_content, encoding="utf-8")
                updated += 1

        # Process recitals
        for recital_file in data["recitals"]:
            num = extract_number(os.path.basename(recital_file))
            if num is None:
                continue

            cross_refs = build_cross_references_for_historical(
                recital_file, "recital", num, version_key, version_data, docs_dir
            )

            if cross_refs:
                content = Path(recital_file).read_text(encoding="utf-8")
                if "\n---\n" in content:
                    parts = content.rsplit("\n---\n", 1)
                    new_content = parts[0] + "\n\n" + cross_refs + "\n\n---\n" + parts[1]
                else:
                    new_content = content + "\n\n" + cross_refs
                Path(recital_file).write_text(new_content, encoding="utf-8")
                updated += 1

    return updated


def build_cross_references_for_historical(file_path, item_type, num, current_version, version_data, docs_dir):
    """Build cross-reference section for a historical file."""
    lines = []
    lines.append("## Internal Cross-References")
    lines.append("")

    # Link to current (final) version
    if item_type == "article":
        current_file = find_current_article(docs_dir, num)
        if current_file:
            rel_path = compute_relative_path(file_path, current_file)
            lines.append(f"**Current version:** [Article {num} (Final)]({rel_path})")
            lines.append("")
    else:
        current_file = find_current_recital(docs_dir, num)
        if current_file:
            rel_path = compute_relative_path(file_path, current_file)
            lines.append(f"**Current version:** [Recital ({num}) (Final)]({rel_path})")
            lines.append("")

    # Links to other historical versions
    lines.append("**Compare versions:**")
    lines.append("")
    for other_version in VERSIONS:
        if other_version == current_version:
            continue
        if other_version not in version_data:
            continue

        other_data = version_data[other_version]
        if item_type == "article":
            nums = other_data["article_nums"]
            if num in nums:
                other_file = os.path.join(docs_dir, "history", other_version, "articles", f"article-{num}.md")
                if os.path.exists(other_file):
                    rel_path = compute_relative_path(file_path, other_file)
                    lines.append(f"- [{VERSIONS[other_version]['name']}]({rel_path})")
        else:
            nums = other_data["recital_nums"]
            if num in nums:
                other_file = os.path.join(docs_dir, "history", other_version, "recitals", f"recital-{num}.md")
                if os.path.exists(other_file):
                    rel_path = compute_relative_path(file_path, other_file)
                    lines.append(f"- [{VERSIONS[other_version]['name']}]({rel_path})")

    return "\n".join(lines)


def add_drafting_history_to_current(docs_dir, version_data):
    """Add drafting history sections to current (final) article and recital pages."""
    updated = 0

    # Process articles
    article_files = glob.glob(os.path.join(docs_dir, "articles", "chapter-*", "article-*.md"))
    for article_file in sorted(article_files):
        num = extract_number(os.path.basename(article_file))
        if num is None:
            continue

        history_section = build_drafting_history_section(
            article_file, "article", num, version_data, docs_dir
        )

        if history_section:
            content = Path(article_file).read_text(encoding="utf-8")
            # Don't add if already present
            if "Drafting History" in content:
                continue
            content = insert_before_footer(content, history_section)
            Path(article_file).write_text(content, encoding="utf-8")
            updated += 1

    # Process recitals
    recital_files = glob.glob(os.path.join(docs_dir, "recitals", "recital-*.md"))
    for recital_file in sorted(recital_files):
        num = extract_number(os.path.basename(recital_file))
        if num is None:
            continue

        history_section = build_drafting_history_section(
            recital_file, "recital", num, version_data, docs_dir
        )

        if history_section:
            content = Path(recital_file).read_text(encoding="utf-8")
            if "Drafting History" in content:
                continue
            content = insert_before_footer(content, history_section)
            Path(recital_file).write_text(content, encoding="utf-8")
            updated += 1

    return updated


def insert_before_footer(content, section):
    """Insert a section before the navigation footer (--- followed by *Navigate:*)."""
    # Look for the navigation footer pattern
    footer_pattern = re.compile(r'\n---\s*\n\s*\*Navigate:\*', re.DOTALL)
    match = footer_pattern.search(content)
    if match:
        insert_pos = match.start()
        return content[:insert_pos] + "\n\n" + section + "\n" + content[insert_pos:]

    # Fallback: insert before last ---
    if "\n---\n" in content:
        idx = content.rfind("\n---\n")
        return content[:idx] + "\n\n" + section + "\n" + content[idx:]

    # No footer found, append
    return content + "\n\n" + section


def build_drafting_history_section(file_path, item_type, num, version_data, docs_dir):
    """Build the collapsible drafting history section for a current file."""
    links = []

    for version_key in VERSIONS:
        if version_key not in version_data:
            continue

        data = version_data[version_key]
        if item_type == "article":
            if num not in data["article_nums"]:
                continue
            hist_file = os.path.join(docs_dir, "history", version_key, "articles", f"article-{num}.md")
        else:
            if num not in data["recital_nums"]:
                continue
            hist_file = os.path.join(docs_dir, "history", version_key, "recitals", f"recital-{num}.md")

        if not os.path.exists(hist_file):
            continue

        rel_path = compute_relative_path(file_path, hist_file)
        links.append(f"    - [{VERSIONS[version_key]['name']}]({rel_path})")

    if not links:
        return None

    lines = [
        '??? info "Drafting History"',
        "    See how this provision evolved through the legislative process:",
        "",
    ]
    lines.extend(links)

    return "\n".join(lines)


def create_version_index(docs_dir, version_key, version_info, version_data):
    """Create an index page for a historical version."""
    if version_key not in version_data:
        return False

    data = version_data[version_key]
    index_path = os.path.join(docs_dir, "history", version_key, "index.md")

    lines = [
        f"# {version_info['name']}",
        "",
        f"**Date:** {version_info['date']}",
        "",
        f"{version_info['description']}.",
        "",
        f"**Source:** [{version_info['name']}]({version_info['source_url']})",
        "",
    ]

    # Articles
    if data["article_nums"]:
        lines.append(f"## Articles ({len(data['article_nums'])})")
        lines.append("")
        for num in data["article_nums"]:
            lines.append(f"- [Article {num}](articles/article-{num}.md)")
        lines.append("")

    # Recitals
    if data["recital_nums"]:
        lines.append(f"## Recitals ({len(data['recital_nums'])})")
        lines.append("")
        for num in data["recital_nums"]:
            lines.append(f"- [Recital ({num})](recitals/recital-{num}.md)")
        lines.append("")

    Path(index_path).write_text("\n".join(lines), encoding="utf-8")
    return True


def create_history_landing_page(docs_dir, version_data):
    """Create the main history landing page."""
    index_path = os.path.join(docs_dir, "history", "index.md")

    lines = [
        "# Drafting History",
        "",
        "Explore how the EU AI Act evolved through the legislative process.",
        "",
        "## Available Versions",
        "",
    ]

    for version_key, version_info in VERSIONS.items():
        if version_key not in version_data:
            continue
        data = version_data[version_key]
        n_articles = len(data["article_nums"])
        n_recitals = len(data["recital_nums"])
        lines.extend([
            f"### [{version_info['name']}]({version_key}/)",
            "",
            version_info["description"],
            "",
            f"- {n_articles} articles",
            f"- {n_recitals} recitals",
            "",
        ])

    lines.extend([
        "## How to Use",
        "",
        "Each article and recital in the current (final) version includes a "
        '"Drafting History" section showing how it evolved through these versions. '
        "Click on any historical version to see the text as it appeared at that stage.",
        "",
        "All cross-references are internal — this is a completely self-contained resource.",
    ])

    Path(index_path).write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Integrate historical AI Act versions")
    parser.add_argument("--docs-dir", required=True, help="Path to the docs/ directory")
    args = parser.parse_args()

    docs_dir = os.path.abspath(args.docs_dir)

    if not os.path.isdir(docs_dir):
        print(f"Error: {docs_dir} is not a directory")
        return

    print("=" * 70)
    print("Self-Contained Drafting History Integration")
    print("=" * 70)
    print()

    # Step 1: Scan versions
    print("🔍 Scanning all versions...")
    version_data = scan_versions(docs_dir)
    for version_key, data in version_data.items():
        n_a = len(data["article_nums"])
        n_r = len(data["recital_nums"])
        print(f"  ✅ {version_key}: {n_a} articles, {n_r} recitals")
    print()

    # Step 2: Add cross-references to historical files
    print("📝 Adding internal cross-references to historical versions...")
    hist_updated = add_cross_references_to_historical(docs_dir, version_data)
    print(f"✅ Updated {hist_updated} historical files with internal cross-references")
    print()

    # Step 3: Add drafting history to current files
    print("📝 Adding drafting history to final version...")
    current_updated = add_drafting_history_to_current(docs_dir, version_data)
    print(f"✅ Updated {current_updated} final version files with drafting history")
    print()

    # Step 4: Create index pages
    print("📄 Creating version index pages...")
    create_history_landing_page(docs_dir, version_data)
    print("  ✅ Created history/index.md")
    for version_key, version_info in VERSIONS.items():
        if create_version_index(docs_dir, version_key, version_info, version_data):
            print(f"  ✅ Created {version_key}/index.md")
    print()

    print("=" * 70)
    print("✅ INTEGRATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
