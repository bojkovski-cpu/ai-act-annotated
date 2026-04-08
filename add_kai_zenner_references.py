#!/usr/bin/env python3
"""
Complete Article-Recital Cross-Reference Mapping
Based on Kai Zenner's official mapping document
"""

# Complete mapping from Kai Zenner's document
# Format: {article_number: [list of related recital numbers]}

ARTICLE_RECITAL_MAPPING = {
    1: [1, 2, 3, 6, 7, 8],
    2: [9, 10, 11, 21, 22, 23, 24, 25, 166],
    3: [12, 13, 14, 15, 16, 17, 18, 19, 97, 98, 99, 100, 110, 128],
    4: [20],
    5: [3, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45],
    6: [46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63],
    7: [51, 52, 53],
    8: [46, 64],
    9: [65],
    10: [66, 67, 68, 69, 70],
    11: [71],
    12: [71],
    13: [72],
    14: [73],
    15: [74, 75, 76, 77, 78],
    16: [79, 80, 81, 145],
    17: [81],
    18: [81],
    19: [81],
    20: [81],
    21: [81],
    22: [82, 83],
    23: [83],
    24: [83],
    25: [83, 84, 85, 86, 87, 88, 89, 90],
    26: [91, 92, 93, 94, 95],
    27: [93, 96],
    # Notifying authorities section (28-39)
    28: [],  # Not explicitly mapped
    29: [],
    30: [],
    31: [145],
    32: [],
    33: [126],
    34: [],
    35: [],
    36: [],
    37: [],
    38: [],
    39: [127],
    40: [121],
    41: [121],
    42: [77, 78, 122],
    43: [78, 123, 124, 125, 126, 128, 147],
    # Additional articles
    45: [],
    46: [130],
    47: [],
    48: [129],
    49: [131],
    50: [132, 133, 134, 135, 136, 137],
    51: [110, 111],
    52: [112, 113],
    53: [101, 102, 103, 104, 105, 106, 107, 108, 109],
    54: [],
    55: [114, 115],
    56: [116, 117],
    57: [138, 139],
    58: [139],
    59: [140],
    60: [141],
    61: [141],
    62: [143],
    63: [146],
    # Chapter VII - Governance
    65: [149],
    66: [149],
    67: [150],
    68: [151],
    69: [151],
    70: [153, 154],
    71: [131],
    72: [155],
    73: [155],
    74: [156],
    75: [161],
    77: [157],
    78: [167],
    # Market surveillance articles
    84: [152],
    85: [170],
    86: [171],
    87: [172],
    88: [162],
    89: [164],
    90: [163],
    91: [164],
    92: [164],
    93: [164],
    94: [164],
    95: [165, 166],
    # Delegation and penalties
    97: [173],
    98: [175],
    99: [168],
    100: [168],
    101: [169],
    # Final provisions (Articles 102-113)
    102: [49],
    103: [49],
    104: [49],
    105: [49],
    106: [49],
    107: [49],
    108: [49],
    109: [49],
    110: [49],
    111: [177],
    112: [174],
    113: [178, 179],
}

def format_recital_links(recitals):
    """Format recital numbers as markdown links"""
    if not recitals:
        return "No specific recitals identified in Kai Zenner's mapping"
    
    links = []
    for r in sorted(recitals):
        links.append(f"[Recital ({r})](../../recitals/recital-{r:03d}.md)")
    return ", ".join(links)

def create_cross_ref_section(article_num):
    """Create the complete cross-reference section for an article"""
    recitals = ARTICLE_RECITAL_MAPPING.get(article_num, [])
    recital_links = format_recital_links(recitals)
    
    return f"""
!!! info "Related Recitals"
    {recital_links}
"""

def update_article_file(article_path, article_num):
    """Update an article file with recital cross-references"""
    try:
        with open(article_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if already has Related Recitals section
        if "Related Recitals" in content:
            print(f"  ⚠️  Article {article_num} already has recital references")
            return False
        
        # Add recital references after Cross-References section, before Official Text
        cross_ref_section = create_cross_ref_section(article_num)
        
        if "## Official Text" in content:
            content = content.replace("## Official Text", cross_ref_section + "\n## Official Text")
            
            with open(article_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        else:
            print(f"  ⚠️  Could not find '## Official Text' marker in Article {article_num}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error processing Article {article_num}: {e}")
        return False

def main():
    """Main function to add all recital cross-references"""
    import os
    from pathlib import Path
    
    # Try both possible locations
    possible_paths = [
        Path("/mnt/user-data/outputs/ai-act-annotated/docs/articles"),
        Path("/home/claude/ai-act-annotated/docs/articles"),
        Path("./ai-act-annotated/docs/articles"),
        Path("./docs/articles"),
    ]
    
    base_path = None
    for path in possible_paths:
        if path.exists():
            base_path = path
            break
    
    if not base_path:
        print("❌ Could not find articles directory.")
        print("   Please run this script from the ai-act-annotated directory")
        print("   or ensure the project has been extracted.")
        return
    
    print(f"📁 Found articles directory: {base_path}")
    print(f"📊 Processing {len(ARTICLE_RECITAL_MAPPING)} articles with recital mappings...\n")
    
    updated_count = 0
    skipped_count = 0
    not_found_count = 0
    
    for article_num in sorted(ARTICLE_RECITAL_MAPPING.keys()):
        # Find the article file in chapter directories
        found = False
        for chapter_dir in sorted(base_path.glob("chapter-*")):
            article_file = chapter_dir / f"article-{article_num:02d}.md"
            if article_file.exists():
                found = True
                recital_count = len(ARTICLE_RECITAL_MAPPING[article_num])
                print(f"Processing Article {article_num} ({recital_count} recitals)...", end=" ")
                
                if update_article_file(article_file, article_num):
                    updated_count += 1
                    print("✅")
                else:
                    skipped_count += 1
                    print("⏭️")
                break
        
        if not found:
            not_found_count += 1
            print(f"❌ Article {article_num} file not found")
    
    print(f"\n" + "="*60)
    print(f"✅ Updated: {updated_count} articles")
    print(f"⏭️  Skipped: {skipped_count} articles (already had references)")
    print(f"❌ Not found: {not_found_count} articles")
    print(f"📊 Total processed: {len(ARTICLE_RECITAL_MAPPING)} articles")
    print(f"="*60)
    
    if updated_count > 0:
        print(f"\n🎉 Success! Added recital cross-references to {updated_count} articles")
        print(f"💡 Next steps:")
        print(f"   1. Review the changes: git diff")
        print(f"   2. Test locally: mkdocs serve")
        print(f"   3. Commit: git add . && git commit -m 'Add Kai Zenner recital cross-references'")
        print(f"   4. Deploy: mkdocs gh-deploy")

if __name__ == "__main__":
    main()
