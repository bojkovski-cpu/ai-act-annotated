# Deployment — Strato VPS via WSL + rsync + Caddy

Ports the site off GitHub Pages onto the Strato VPS that already runs FreshRSS + n8n. Mirrors the GDPR Annotated Edition's `deployment/deploy.sh` pattern (**Verify** — confirm the pattern matches by diffing with that project's `deploy.sh` before relying on this for production cutover).

## Layout

```
deployment/
├── deploy.sh               # WSL-side deploy script. npm run build (unless --skip-build), then rsync dist/ to VPS.
├── .env.deploy.example     # Template for VPS_HOST, VPS_USER, VPS_PATH. Copy to .env.deploy (gitignored).
├── .env.deploy             # Your private config. NEVER commit.
├── Caddyfile.aiact.snippet # Caddy site block for aiact.annotated.nl. Append to /etc/caddy/Caddyfile on the VPS.
└── README.md               # This file.
```

## First-time setup (one-time per machine)

### On the VPS (Strato)

1. Create the deploy target directory and set ownership:
   ```bash
   sudo mkdir -p /var/www/aiact.annotated.nl
   sudo chown -R <VPS_USER>:<VPS_USER> /var/www/aiact.annotated.nl
   ```

2. Add the Caddy block. Open `/etc/caddy/Caddyfile` and append the contents of `deployment/Caddyfile.aiact.snippet` (or use a separate imported file if your Caddyfile is modular).

3. Validate and reload Caddy:
   ```bash
   sudo caddy validate --config /etc/caddy/Caddyfile
   sudo systemctl reload caddy
   ```

4. **Before DNS cutover**, test directly by hostname. The TLS cert won't mint until DNS points at the VPS, so the first test will be either plain HTTP or an override in `/etc/hosts` on your workstation.

### On your workstation (WSL on Windows)

1. Copy `.env.deploy.example` to `.env.deploy` and fill in:
   - `VPS_HOST` — the Strato VPS hostname or IP
   - `VPS_USER` — SSH user (the one you created `/var/www/aiact.annotated.nl` as)
   - `VPS_PATH` — `/var/www/aiact.annotated.nl` (must match `root` in the Caddyfile block)

2. Make sure SSH to the VPS works without a password prompt (ssh-agent or key file).

3. Ensure `rsync` is installed in WSL: `sudo apt install rsync` (usually already present on Ubuntu).

4. From PowerShell on Windows, run `npm ci` and `npm run build` once to verify the build succeeds. WSL can then invoke the deploy with `--skip-build` (or let deploy.sh run `npm run build` itself if you're doing everything inside WSL).

## Normal deploy workflow

**Option A — build on Windows, rsync from WSL (recommended, matches GDPR pattern):**
```powershell
# In PowerShell, from the repo root
npm run build
```
```bash
# In WSL, from the repo root
./deployment/deploy.sh --skip-build
```

**Option B — build and deploy all inside WSL:**
```bash
./deployment/deploy.sh
```

## DNS cutover (aiact.annotated.nl → Strato VPS)

Memory note: DNS is hosted at Strato itself (not DuckDNS). The cutover is:

1. Confirm the site is accessible on the VPS via IP or hostname override.
2. Update the A record for `aiact.annotated.nl` in the Strato DNS panel to the VPS IPv4 address.
3. (Optional) add an AAAA record if the VPS has IPv6.
4. TTL: Strato's default is typically 3600s. Drop to 300s a day before cutover for fast rollback.
5. Watch DNS propagation: `dig aiact.annotated.nl @1.1.1.1` from WSL.
6. When propagated, Caddy will automatically mint a Let's Encrypt cert on first hit.
7. Verify: `curl -I https://aiact.annotated.nl/` returns 200 with `content-type: text/html`.
8. Retire the GitHub Pages deploy workflow (`.github/workflows/deploy.yml`) — set to `workflow_dispatch` only, or delete.

## Rollback

If the VPS deploy goes bad, revert DNS at Strato to the GitHub Pages IPs (`185.199.108.153`, `.109.153`, `.110.153`, `.111.153`). GH Pages still serves (until retired in step 3.6), so this is instant.

## Gotchas

- **Caddy's ACME challenge needs port 80 open.** Strato's firewall panel — confirm 80 and 443 are allowed inbound.
- **Trailing slash consistency.** `astro.config.mjs` now has `trailingSlash: 'always'`. Astro builds `page/index.html`, not `page.html`. Caddy's `file_server` handles this natively.
- **rsync `--delete` removes orphan files on the VPS** that aren't in the current `dist/`. Don't stash anything in `VPS_PATH` that you want kept.
- **Strato VPS disk limits.** Check `df -h` on the VPS. Site is ~10-20 MB built, not a concern on its own, but if you're also running FreshRSS + n8n, monitor.
