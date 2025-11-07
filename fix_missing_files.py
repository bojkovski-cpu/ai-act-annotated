#!/usr/bin/env python3
"""
Fix missing files in the AI Act annotated site
"""

from pathlib import Path

def create_missing_recitals():
    """Create recital files 100-180 that are missing"""
    base_path = Path("docs/recitals")
    base_path.mkdir(parents=True, exist_ok=True)
    
    created = 0
    for i in range(100, 181):
        filepath = base_path / f"recital-{i:03d}.md"
        if not filepath.exists():
            content = f"""---
title: Recital ({i})
tags: []
---

# Recital ({i})

## Official Text

[Official text to be added from AI Act PDF]

## Key Points

[To be added based on analysis]

## Cross-References

### Related Articles

[To be identified]

### Related Recitals

[To be identified]

## Commentary

!!! note "Your Commentary"
    Add your analysis and interpretation here.

---

*Navigate:* 
[← Previous](recital-{i-1:03d}.md) | 
[Recitals Index](index.md) | 
{"[Next →](recital-" + f"{i+1:03d}.md)" if i < 180 else "[Articles →](../articles/chapter-01/index.md)"}
"""
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            created += 1
            print(f"✅ Created recital-{i:03d}.md")
    
    return created

def create_chapter_indexes():
    """Create missing chapter index files"""
    chapters = {
        2: ("Chapter II", "Prohibited AI Practices", 1, [5]),
        3: ("Chapter III", "High-Risk AI Systems", 46, list(range(6, 50))),
        4: ("Chapter IV", "Transparency Obligations", 1, [50]),  
        5: ("Chapter V", "General-Purpose AI Models", 4, [51, 52, 53, 54, 55, 56]),
        6: ("Chapter VI", "Innovation Support", 7, list(range(57, 64))),
        7: ("Chapter VII", "Governance", 7, list(range(64, 71))),
        8: ("Chapter VIII", "EU Database", 1, [71]),
        9: ("Chapter IX", "Post-Market Monitoring", 23, list(range(72, 95))),
        10: ("Chapter X", "Codes of Conduct", 2, [95, 96]),
        11: ("Chapter XI", "Delegation of Power", 2, [97, 98]),
        12: ("Chapter XII", "Penalties", 3, [99, 100, 101]),
        13: ("Chapter XIII", "Final Provisions", 13, list(range(102, 114))),
    }
    
    created = 0
    for num, (title, desc, count, articles) in chapters.items():
        filepath = Path(f"docs/articles/chapter-{num:02d}/index.md")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        if not filepath.exists():
            # Build article list
            article_list = "\n".join([
                f"- [Article {a}](article-{a:02d}.md)" for a in articles[:5]
            ])
            if len(articles) > 5:
                article_list += f"\n- ... and {len(articles) - 5} more"
            
            content = f"""# {title} - {desc}

## Overview

{desc} provisions of the EU AI Act.

## Articles in This Chapter

{article_list}

## Key Points

[Add chapter-specific overview]

## Implementation Notes

[Add compliance guidance]

---

**Navigation:** 
[← Previous Chapter](../chapter-{num-1:02d}/index.md) | 
[Home](../../index.md) | 
{"[Next Chapter →](../chapter-" + f"{num+1:02d}/index.md)" if num < 13 else ""}
"""
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            created += 1
            print(f"✅ Created chapter-{num:02d}/index.md")
    
    return created

def create_support_pages():
    """Create missing support pages"""
    pages = {
        "key-concepts.md": """# Key Concepts

## Core Definitions

### AI System
[Definition and explanation]

### High-Risk AI
[Definition and explanation]

### Provider
[Definition and explanation]

### Deployer
[Definition and explanation]

[Add more key concepts]
""",
        "cross-references/index.md": """# Cross-References

Connections between the AI Act and other EU regulations.

- [GDPR Mapping](gdpr.md)
- [DSA Mapping](dsa.md)
- [DMA Mapping](dma.md)
- [Product Safety](product-safety.md)
""",
        "cross-references/gdpr.md": """# GDPR Cross-References

Mapping between AI Act and GDPR provisions.

[To be developed]
""",
        "cross-references/dsa.md": """# DSA Cross-References

Mapping between AI Act and Digital Services Act.

[To be developed]
""",
        "cross-references/dma.md": """# DMA Cross-References

Mapping between AI Act and Digital Markets Act.

[To be developed]
""",
        "cross-references/product-safety.md": """# Product Safety Cross-References

Connections to product safety legislation.

[To be developed]
""",
        "annexes/index.md": """# Annexes

The AI Act includes 13 annexes with technical details.

[To be developed]
""",
        "guidance/compliance-checklist.md": """# Compliance Checklist

Step-by-step guide to AI Act compliance.

[To be developed]
""",
        "guidance/implementation-timeline.md": """# Implementation Timeline

Key dates and milestones for AI Act compliance.

[To be developed]
""",
        "guidance/industry-guides/healthcare.md": """# Healthcare AI Guidance

Industry-specific compliance guidance.

[To be developed]
""",
        "guidance/industry-guides/finance.md": """# Financial Services AI Guidance

Industry-specific compliance guidance.

[To be developed]
""",
        "guidance/industry-guides/employment.md": """# Employment AI Guidance

Industry-specific compliance guidance.

[To be developed]
""",
        "guidance/industry-guides/law-enforcement.md": """# Law Enforcement AI Guidance

Industry-specific compliance guidance.

[To be developed]
""",
        "resources/glossary.md": """# Glossary

Key terms and definitions.

[To be developed]
""",
        "resources/faq.md": """# FAQ

Frequently asked questions.

[To be developed]
""",
        "resources/external-links.md": """# External Links

Useful resources and references.

[To be developed]
""",
        "resources/about.md": """# About This Site

Information about the annotated AI Act project.

[To be developed]
""",
    }
    
    created = 0
    for filepath, content in pages.items():
        full_path = Path("docs") / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not full_path.exists():
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            created += 1
            print(f"✅ Created {filepath}")
    
    return created

def main():
    """Run all fixes"""
    print("🔧 Fixing missing files in AI Act project...\n")
    
    print("1️⃣ Creating missing recitals (100-180)...")
    recitals = create_missing_recitals()
    print(f"   Created {recitals} recital files\n")
    
    print("2️⃣ Creating missing chapter indexes...")
    chapters = create_chapter_indexes()
    print(f"   Created {chapters} chapter index files\n")
    
    print("3️⃣ Creating missing support pages...")
    support = create_support_pages()
    print(f"   Created {support} support pages\n")
    
    print("="*60)
    print(f"✅ COMPLETE!")
    print(f"   - {recitals} recital files")
    print(f"   - {chapters} chapter indexes")
    print(f"   - {support} support pages")
    print(f"   - Total: {recitals + chapters + support} files created")
    print("="*60)
    print(f"\n💡 Next steps:")
    print(f"   1. Run 'mkdocs serve' to test")
    print(f"   2. Commit changes: git add . && git commit -m 'Fix missing files'")
    print(f"   3. Deploy: mkdocs gh-deploy")

if __name__ == "__main__":
    main()
