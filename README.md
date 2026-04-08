# Annotated EU AI Act

> Comprehensive annotated edition of the EU Artificial Intelligence Act (Regulation EU 2024/1689) with cross-references, commentary, and implementation guidance.

🌐 **Live Site:** [https://bojkovski-cpu.github.io/ai-act-annotated](https://bojkovski-cpu.github.io/ai-act-annotated)

## Features

- ✅ **Complete Official Text** - All 114 articles and 138 recitals
- 🔗 **Cross-References** - Internal and external regulatory connections
- 📝 **Commentary Framework** - Spaces for legal analysis and practical guidance
- 🔍 **Full-Text Search** - Find any provision or concept instantly
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile
- 🌓 **Dark Mode** - Easy on the eyes
- 📄 **Print-Friendly** - Generate PDFs of any page
- 🏷️ **Tagged Content** - Organized by topic and provision type

## Quick Start

### Prerequisites

- Python 3.8+
- pip (Python package manager)
- Git

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/bojkovski-cpu/ai-act-annotated.git
   cd ai-act-annotated
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run local server**
   ```bash
   mkdocs serve
   ```

4. **View in browser**
   Open [http://localhost:8000](http://localhost:8000)

The site will automatically reload when you make changes to files.

## Project Structure

```
ai-act-annotated/
├── docs/                          # All content files
│   ├── index.md                   # Homepage
│   ├── introduction.md
│   ├── how-to-use.md
│   │
│   ├── recitals/                  # 138 recital files
│   │   ├── index.md
│   │   ├── recital-001.md
│   │   └── ...
│   │
│   ├── articles/                  # 114 article files
│   │   ├── chapter-01/            # 13 chapter directories
│   │   │   ├── index.md
│   │   │   ├── article-01.md
│   │   │   └── ...
│   │   └── ...
│   │
│   ├── annexes/                   # 13 annexes
│   ├── cross-references/          # Regulatory mappings
│   ├── guidance/                  # Compliance guidance
│   ├── resources/                 # Glossary, FAQ, etc.
│   │
│   ├── stylesheets/
│   │   └── extra.css              # Custom styling
│   └── javascripts/
│       └── extra.js               # Custom JavaScript
│
├── overrides/                     # Theme customizations
│   └── partials/
│
├── mkdocs.yml                     # Site configuration
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Content Organization

### Recitals (138)
Located in `docs/recitals/`, these provide legislative context and interpretation guidance.

### Articles (114 across 13 chapters)
Located in `docs/articles/chapter-XX/`, organized by chapter:
- Chapter I: General Provisions (Articles 1-4)
- Chapter II: Prohibited Practices (Article 5)
- Chapter III: High-Risk AI Systems (Articles 6-51)
- Chapter IV: Transparency Obligations (Article 52)
- Chapter V: General-Purpose AI (Articles 53-56)
- Chapters VI-XIII: Governance, enforcement, final provisions

### Cross-References
Mappings between the AI Act and:
- GDPR (General Data Protection Regulation)
- DSA (Digital Services Act)
- DMA (Digital Markets Act)
- Product Safety Regulations
- Other relevant EU legislation

## Editing Content

### Markdown Files
All content is in Markdown format (`.md` files). To edit:

1. Open the file in any text editor
2. Make changes using Markdown syntax
3. Save the file
4. Changes appear automatically in local development server

### Adding Commentary

Each article has a commentary section. Add your analysis in the orange box:

```markdown
## Commentary

!!! note "Your Commentary"
    Add your legal analysis, compliance guidance, and practical insights here.
    
    Use **bold** for emphasis, [links](url) for references, and:
    - Bullet points
    - For structured content
```

### Adding Cross-References

Update the cross-reference boxes in blue:

```markdown
!!! info "Internal (AI Act)"
    - [Article 1 - Subject Matter](../chapter-01/article-01.md)
    - [Article 6 - Classification](article-06.md)
    
!!! info "Related Regulations"
    - GDPR Article 5 - Principles of data processing
    - DSA Article 24 - Transparency
```

## Deployment to GitHub Pages

### Initial Setup

1. **Create GitHub repository**
   ```bash
   # Already done at: https://github.com/bojkovski-cpu/ai-act-annotated
   ```

2. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Initial commit: AI Act annotated site"
   git remote add origin https://github.com/bojkovski-cpu/ai-act-annotated.git
   git push -u origin main
   ```

3. **Deploy to GitHub Pages**
   ```bash
   mkdocs gh-deploy
   ```

This creates/updates the `gh-pages` branch and publishes your site.

### Continuous Deployment

Every time you want to update the live site:

1. **Make changes** to markdown files
2. **Test locally** with `mkdocs serve`
3. **Commit changes**
   ```bash
   git add .
   git commit -m "Update: description of changes"
   git push origin main
   ```
4. **Deploy**
   ```bash
   mkdocs gh-deploy
   ```

The site updates at `https://bojkovski-cpu.github.io/ai-act-annotated` within minutes.

### GitHub Actions (Automatic Deployment)

Optionally, set up automatic deployment on every push:

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-python@v4
        with:
          python-version: 3.x
      
      - run: pip install -r requirements.txt
      
      - run: mkdocs gh-deploy --force
```

With this, the site automatically deploys when you push to `main`.

## Custom Domain (Optional)

To use a custom domain (e.g., `ai-act-annotated.com`):

1. **Purchase domain** from registrar
2. **Add CNAME file** to `docs/`:
   ```
   echo "your-domain.com" > docs/CNAME
   ```
3. **Configure DNS** at your registrar:
   - Add CNAME record: `www` → `bojkovski-cpu.github.io`
   - Add A records for apex domain:
     - `185.199.108.153`
     - `185.199.109.153`
     - `185.199.110.153`
     - `185.199.111.153`
4. **Update `mkdocs.yml`**:
   ```yaml
   site_url: https://your-domain.com
   ```
5. **Deploy** with `mkdocs gh-deploy`

## Contributing

### Adding New Content

1. Create new `.md` file in appropriate directory
2. Add entry to `nav:` section in `mkdocs.yml`
3. Use existing pages as templates
4. Test locally before deploying

### Style Guide

- **Headings:** Use sentence case
- **Links:** Descriptive text, not "click here"
- **Lists:** Use for multiple related items
- **Tables:** For structured comparisons
- **Admonitions:** Use colored boxes for special content:
  - `!!! info` - Cross-references (blue)
  - `!!! note` - Commentary (orange)
  - `!!! tip` - Practical guidance (green)
  - `!!! warning` - Important notices (yellow)

## Dependencies

Key Python packages (see `requirements.txt`):

```
mkdocs>=1.5.0
mkdocs-material>=9.4.0
pymdown-extensions>=10.0
mkdocs-git-revision-date-localized-plugin>=1.2.0
```

## Customization

### Theme Colors

Edit `mkdocs.yml` under `theme.palette`:

```yaml
palette:
  primary: blue      # Header/navigation color
  accent: indigo     # Links and highlights
```

### Custom CSS

Add styles to `docs/stylesheets/extra.css`.

### Custom JavaScript

Add scripts to `docs/javascripts/` and reference in `mkdocs.yml`.

## License

### Content
The official text of the EU AI Act is © European Union and used under fair use for educational purposes.

### Original Commentary & Annotations
All original commentary, cross-references, and guidance added to this site are available under the MIT License.

### Code
The site code and structure are available under the MIT License.

See [LICENSE](LICENSE) for details.

## Acknowledgments

- **Official Text:** European Union, Regulation (EU) 2024/1689
- **Framework:** MkDocs with Material theme
- **Hosting:** GitHub Pages

## Contact

For questions, suggestions, or issues:
- **GitHub Issues:** [Report a problem](https://github.com/bojkovski-cpu/ai-act-annotated/issues)
- **GitHub Discussions:** [Ask questions](https://github.com/bojkovski-cpu/ai-act-annotated/discussions)

## Status

- ✅ Structure complete
- ✅ All 138 recitals extracted
- ✅ All 114 articles extracted  
- 🔄 Cross-references being enhanced
- 🔄 Commentary being added
- 🔄 Annexes being formatted

**Last Updated:** November 2024  
**Version:** 1.0.0  
**AI Act Version:** Regulation (EU) 2024/1689 (12 July 2024)

---

**Made with ❤️ for the AI compliance community**
