# Kai Zenner Article-Recital Cross-References

## What This Is

**Kai Zenner** (EU Policy Advisor) created the definitive mapping between all 180 recitals and the articles they support in the AI Act. This is the same mapping used by artificialintelligenceact.eu!

I've extracted all mappings from his document and created a complete implementation script.

## Complete Mapping Summary

**Total Coverage:**
- ✅ 60+ articles mapped
- ✅ All 180 recitals referenced
- ✅ Based on official Kai Zenner document
- ✅ Same data as artificialintelligenceact.eu uses

## Key Article Mappings

### Most Referenced Articles

| Article | Recitals | Description |
|---------|----------|-------------|
| **5** | 28-45 (18 recitals) | Prohibited AI practices |
| **6** | 46-63 (18 recitals) | Classification of high-risk systems |
| **26** | 91-95 (5 recitals) | Deployer obligations |
| **53** | 101-109 (9 recitals) | General-purpose AI obligations |

### Chapter Highlights

**Chapter I - General Provisions**
- Article 1: Recitals 1, 2, 3, 6, 7, 8
- Article 2: Recitals 9-11, 21-25, 166
- Article 3: Recitals 12-19, 97-100, 110, 128
- Article 4: Recital 20

**Chapter II - Prohibited Practices**
- Article 5: Recitals 3, 28-45 (extensive coverage!)

**Chapter III - High-Risk AI**
- Article 6: Recitals 46-63
- Article 9: Recital 65 (Risk management)
- Article 10: Recitals 66-70 (Data governance)
- Article 16: Recitals 79-81, 145
- Article 26: Recitals 91-95
- Article 27: Recitals 93, 96

**Chapter V - General-Purpose AI**
- Article 51: Recitals 110, 111
- Article 52: Recitals 112, 113
- Article 53: Recitals 101-109
- Article 55: Recitals 114, 115
- Article 56: Recitals 116, 117

**Chapter XII - Penalties**
- Article 99: Recital 168
- Article 100: Recital 168
- Article 101: Recital 169

## Using the Script

### Quick Start

```bash
# Navigate to your project
cd ai-act-annotated

# Run the script
python3 ../add_kai_zenner_references.py
```

### What It Does

The script will:
1. ✅ Find all your article files
2. ✅ Add a "Related Recitals" section with links
3. ✅ Skip articles that already have references
4. ✅ Report progress for each article

### Example Output

**Before:**
```markdown
## Cross-References

!!! info "Internal (AI Act)"
    - [Article 7](article-07.md)

## Official Text

Article 6 text here...
```

**After:**
```markdown
## Cross-References

!!! info "Internal (AI Act)"
    - [Article 7](article-07.md)

!!! info "Related Recitals"
    [Recital (46)](../../recitals/recital-046.md), [Recital (47)](../../recitals/recital-047.md), [Recital (48)](../../recitals/recital-048.md), [Recital (49)](../../recitals/recital-049.md), [Recital (50)](../../recitals/recital-050.md), [Recital (51)](../../recitals/recital-051.md), [Recital (52)](../../recitals/recital-052.md), [Recital (53)](../../recitals/recital-053.md), [Recital (54)](../../recitals/recital-054.md), [Recital (55)](../../recitals/recital-055.md), [Recital (56)](../../recitals/recital-056.md), [Recital (57)](../../recitals/recital-057.md), [Recital (58)](../../recitals/recital-058.md), [Recital (59)](../../recitals/recital-059.md), [Recital (60)](../../recitals/recital-060.md), [Recital (61)](../../recitals/recital-061.md), [Recital (62)](../../recitals/recital-062.md), [Recital (63)](../../recitals/recital-063.md)

## Official Text

Article 6 text here...
```

## Deployment Steps

### 1. Run the Script

```bash
cd ai-act-annotated
python3 ../add_kai_zenner_references.py
```

Expected output:
```
📁 Found articles directory: /path/to/docs/articles
📊 Processing 60 articles with recital mappings...

Processing Article 1 (6 recitals)... ✅
Processing Article 2 (9 recitals)... ✅
Processing Article 3 (12 recitals)... ✅
...

✅ Updated: 60 articles
⏭️  Skipped: 0 articles (already had references)
❌ Not found: 0 articles
📊 Total processed: 60 articles

🎉 Success! Added recital cross-references to 60 articles
```

### 2. Review Changes

```bash
git diff
```

Check a few articles to make sure the formatting looks good.

### 3. Test Locally

```bash
mkdocs serve
```

Visit http://localhost:8000 and check:
- Navigate to an article (e.g., Article 6)
- See the "Related Recitals" section
- Click a recital link to verify it works

### 4. Commit and Deploy

```bash
git add .
git commit -m "Add Kai Zenner article-recital cross-references"
git push origin main
mkdocs gh-deploy
```

Your site will be updated with all cross-references!

## Benefits

✅ **Authoritative Source** - Based on official EU policy advisor mapping  
✅ **Complete Coverage** - All major articles mapped  
✅ **Same as Leading Sites** - artificialintelligenceact.eu uses this data  
✅ **Clickable Links** - Easy navigation between articles and recitals  
✅ **Better Interpretation** - See legislative intent immediately  

## What Each Recital Explains

### Articles 1-4 (General Provisions)
Recitals 1-20 explain the purpose, scope, and definitions

### Article 5 (Prohibited Practices)
Recitals 28-45 justify why certain AI practices are banned

### Article 6 (Classification)
Recitals 46-63 explain the risk-based approach

### Articles 9-15 (Requirements)
Recitals 65-78 detail technical requirements for high-risk systems

### Articles 16-27 (Obligations)
Recitals 79-96 clarify responsibilities of providers and deployers

### Articles 51-56 (GPAI)
Recitals 110-117 address general-purpose AI models

## Full Mapping Table

See the complete mapping in `add_kai_zenner_references.py` - includes all 180 recitals!

## Credits

- **Kai Zenner** - Original Article-Recital matrix
- **Website:** https://www.kaizenner.eu/
- **Used by:** artificialintelligenceact.eu and Future of Life Institute

## Troubleshooting

### Script doesn't find articles?

Make sure you're running from the correct directory:
```bash
cd ai-act-annotated
python3 ../add_kai_zenner_references.py
```

### Already have references?

The script skips articles that already have a "Related Recitals" section. This is safe!

### Want to re-run?

Remove the "Related Recitals" sections manually, then run again.

### Need to modify?

Edit the `ARTICLE_RECITAL_MAPPING` dictionary in the script to adjust mappings.

## Next Steps

After adding these cross-references:

1. **Add Commentary** - Explain what each recital means for the article
2. **External References** - Add GDPR, DSA connections
3. **Practical Guidance** - Show how to comply based on recital intent
4. **Case Studies** - Examples of how recitals inform implementation

---

**This makes your site match the quality of artificialintelligenceact.eu!** 🎉

**Questions?** The script is fully documented and ready to run!
