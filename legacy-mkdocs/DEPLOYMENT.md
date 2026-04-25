# 🚀 Deployment Guide for GitHub Pages

This guide will walk you through deploying your AI Act annotated site to GitHub Pages.

## Prerequisites Checklist

- [ ] GitHub account (username: bojkovski-cpu)
- [ ] Git installed on your computer
- [ ] Python 3.8+ installed
- [ ] Terminal/Command Prompt access

## Step-by-Step Deployment

### Step 1: Install Python Dependencies

Open your terminal and navigate to the project directory, then install required packages:

```bash
# Navigate to project directory
cd /path/to/ai-act-annotated

# Install dependencies
pip install -r requirements.txt
```

Expected output:
```
Successfully installed mkdocs-1.5.3 mkdocs-material-9.4.14 ...
```

### Step 2: Test Locally (Optional but Recommended)

Before deploying, test the site locally:

```bash
mkdocs serve
```

You should see:
```
INFO     -  Building documentation...
INFO     -  Cleaning site directory
INFO     -  Documentation built in 2.34 seconds
INFO     -  [16:20:30] Serving on http://127.0.0.1:8000/
```

Open http://127.0.0.1:8000/ in your browser to preview.

Press `Ctrl+C` to stop the server when done.

### Step 3: Initialize Git Repository

If not already done:

```bash
# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: AI Act annotated edition"
```

### Step 4: Create GitHub Repository

1. **Go to GitHub**: https://github.com/new
2. **Repository name**: `ai-act-annotated`
3. **Description**: `Annotated EU AI Act with cross-references and commentary`
4. **Visibility**: Choose Public or Private
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **"Create repository"**

### Step 5: Connect Local Repository to GitHub

GitHub will show commands like these - run them:

```bash
# Add GitHub as remote
git remote add origin https://github.com/bojkovski-cpu/ai-act-annotated.git

# Set default branch to main
git branch -M main

# Push to GitHub
git push -u origin main
```

You may need to authenticate with GitHub:
- Use GitHub CLI, or
- Use personal access token, or
- Set up SSH keys

### Step 6: Deploy to GitHub Pages

Now deploy the site:

```bash
mkdocs gh-deploy
```

This command will:
1. Build the site
2. Create/update the `gh-pages` branch
3. Push the built site to GitHub

Expected output:
```
INFO     -  Cleaning site directory
INFO     -  Building documentation to directory: /tmp/.../site
INFO     -  Documentation built in 2.45 seconds
INFO     -  Copying '/tmp/.../site' to 'gh-pages' branch and pushing to GitHub.
INFO     -  Your documentation should shortly be available at:
            https://bojkovski-cpu.github.io/ai-act-annotated/
```

### Step 7: Enable GitHub Pages (If Needed)

GitHub usually enables Pages automatically, but if not:

1. Go to your repository: https://github.com/bojkovski-cpu/ai-act-annotated
2. Click **Settings** tab
3. Scroll to **Pages** section (left sidebar)
4. Under **Source**, select:
   - Branch: `gh-pages`
   - Folder: `/ (root)`
5. Click **Save**

### Step 8: Access Your Site

Your site will be live at:

**https://bojkovski-cpu.github.io/ai-act-annotated/**

It may take 1-3 minutes for the site to appear after first deployment.

## Making Updates

### Workflow for Updating Content

1. **Edit files** - Make changes to any `.md` files in `docs/`

2. **Test locally** (optional):
   ```bash
   mkdocs serve
   ```

3. **Commit changes**:
   ```bash
   git add .
   git commit -m "Update: describe your changes"
   ```

4. **Push to GitHub**:
   ```bash
   git push origin main
   ```

5. **Deploy**:
   ```bash
   mkdocs gh-deploy
   ```

Your changes will be live within 1-2 minutes.

## Troubleshooting

### Issue: "mkdocs: command not found"

**Solution**: Install MkDocs
```bash
pip install mkdocs mkdocs-material
```

### Issue: "Permission denied" when pushing to GitHub

**Solution**: Set up authentication

Option A - Personal Access Token:
1. Go to GitHub Settings > Developer Settings > Personal Access Tokens
2. Generate new token with `repo` scope
3. Use token as password when prompted

Option B - SSH Keys:
1. Follow: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

### Issue: Site shows 404 error

**Solutions**:
1. Wait 3-5 minutes (first deployment takes time)
2. Check GitHub Pages settings (Step 7 above)
3. Verify `gh-pages` branch exists
4. Try deploying again: `mkdocs gh-deploy`

### Issue: Changes not appearing on live site

**Solutions**:
1. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
2. Wait a few minutes for GitHub to rebuild
3. Check you deployed: `mkdocs gh-deploy` (not just `git push`)

### Issue: "Failed to build" error

**Solution**: Check for Markdown syntax errors
```bash
# Test build locally
mkdocs build --strict
```

Fix any errors shown, then deploy again.

## Automatic Deployment (Optional)

To automatically deploy when you push to GitHub:

### Create GitHub Action

Create file `.github/workflows/deploy.yml`:

```yaml
name: Deploy MkDocs to GitHub Pages

on:
  push:
    branches:
      - main

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-python@v4
        with:
          python-version: 3.x
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Deploy to GitHub Pages
        run: mkdocs gh-deploy --force
```

Commit and push:
```bash
git add .github/workflows/deploy.yml
git commit -m "Add automatic deployment workflow"
git push origin main
```

Now every push to `main` automatically deploys the site!

## Custom Domain (Optional)

To use your own domain (e.g., `ai-act-annotated.com`):

1. **Purchase domain** from registrar (Namecheap, Google Domains, etc.)

2. **Add CNAME file**:
   ```bash
   echo "your-domain.com" > docs/CNAME
   git add docs/CNAME
   git commit -m "Add custom domain"
   git push origin main
   mkdocs gh-deploy
   ```

3. **Configure DNS** at your domain registrar:
   
   Add these records:
   ```
   Type: CNAME
   Name: www
   Value: bojkovski-cpu.github.io
   
   Type: A
   Name: @
   Value: 185.199.108.153
   
   Type: A
   Name: @
   Value: 185.199.109.153
   
   Type: A  
   Name: @
   Value: 185.199.110.153
   
   Type: A
   Name: @
   Value: 185.199.111.153
   ```

4. **Update mkdocs.yml**:
   ```yaml
   site_url: https://your-domain.com
   ```

5. **Deploy**: `mkdocs gh-deploy`

DNS propagation takes 24-48 hours.

## Monitoring & Analytics (Optional)

### Add Google Analytics

1. Create Google Analytics property
2. Copy Measurement ID (e.g., `G-XXXXXXXXXX`)
3. Edit `mkdocs.yml`:
   ```yaml
   extra:
     analytics:
       provider: google
       property: G-XXXXXXXXXX
   ```
4. Deploy: `mkdocs gh-deploy`

## Support

### Need Help?

- **Documentation**: https://www.mkdocs.org/
- **Material Theme**: https://squidfunk.github.io/mkdocs-material/
- **GitHub Pages**: https://docs.github.com/en/pages

### Common Commands Reference

```bash
# Test locally
mkdocs serve

# Build site (don't deploy)
mkdocs build

# Deploy to GitHub Pages
mkdocs gh-deploy

# Check for errors
mkdocs build --strict

# View MkDocs version
mkdocs --version
```

## Next Steps

- ✅ Site is now live
- 📝 Start adding your commentary to articles
- 🔗 Enhance cross-references
- 📊 Add industry-specific guidance
- 🔄 Keep content updated

---

**Your site is now deployed!** 🎉

Visit: **https://bojkovski-cpu.github.io/ai-act-annotated/**

Questions? Check the [README](../README.md) or open an issue on GitHub.
