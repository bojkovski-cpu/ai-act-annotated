#!/usr/bin/env python3
"""
Fix relative link warnings in markdown files
"""

import re
from pathlib import Path

def fix_file_links(filepath):
    """Fix relative links in a file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Fix links that start with ../ when they shouldn't
        # Pattern: ../something.md should be something.md when in same directory
        content = re.sub(r'\.\./([a-z-]+\.md)', r'\1', content)
        
        # Fix directory links: articles/chapter-01/ -> articles/chapter-01/index.md
        content = re.sub(r'\(articles/chapter-(\d+)/\)', r'(articles/chapter-\1/index.md)', content)
        content = re.sub(r'\(\.\./articles/chapter-(\d+)/\)', r'(../articles/chapter-\1/index.md)', content)
        
        # Fix recitals/ -> recitals/index.md
        content = re.sub(r'\(recitals/\)', r'(recitals/index.md)', content)
        content = re.sub(r'\(\.\./recitals/\)', r'(../recitals/index.md)', content)
        
        # Fix cross-references/ -> cross-references/index.md
        content = re.sub(r'\(cross-references/\)', r'(cross-references/index.md)', content)
        content = re.sub(r'\(\.\./cross-references/\)', r'(../cross-references/index.md)', content)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error in {filepath}: {e}")
    return False

def main():
    """Fix all markdown files"""
    docs_path = Path("docs")
    
    if not docs_path.exists():
        print("❌ docs/ directory not found. Run from project root.")
        return
    
    fixed = 0
    for md_file in docs_path.rglob("*.md"):
        if fix_file_links(md_file):
            fixed += 1
            print(f"✅ Fixed {md_file}")
    
    print(f"\n✅ Fixed {fixed} files with link issues")
    print("💡 Run 'mkdocs serve' again to verify warnings are gone")

if __name__ == "__main__":
    main()
