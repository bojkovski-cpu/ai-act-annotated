#!/usr/bin/env bash
# Deploy the built Astro site to the Strato VPS.
#
# USAGE (from WSL):
#   ./deployment/deploy.sh              # build locally (npm run build), then rsync
#   ./deployment/deploy.sh --skip-build # skip build, rsync existing dist/
#
# VERIFY THIS AGAINST THE GDPR ANNOTATED EDITION'S deploy.sh BEFORE FIRST USE.
# Memory note 2026-04-24: pattern was borrowed from the GDPR project. If the GDPR
# version differs in rsync flags, ssh options, or post-deploy steps, sync this to match.
#
# The script expects deployment/.env.deploy to define:
#   VPS_HOST         e.g. aiact.example.strato-vps.de OR an IP
#   VPS_USER         e.g. deploy
#   VPS_PATH         e.g. /var/www/aiact.annotated.nl
#   SSH_PORT         e.g. 22
#   SSH_KEY          optional path to SSH private key (otherwise ssh-agent)

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$REPO_DIR"

# Load env
if [[ ! -f "$SCRIPT_DIR/.env.deploy" ]]; then
    echo "ERROR: $SCRIPT_DIR/.env.deploy not found."
    echo "Copy .env.deploy.example and fill in VPS_HOST, VPS_USER, VPS_PATH."
    exit 1
fi
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.env.deploy"

: "${VPS_HOST:?VPS_HOST not set in .env.deploy}"
: "${VPS_USER:?VPS_USER not set in .env.deploy}"
: "${VPS_PATH:?VPS_PATH not set in .env.deploy}"
SSH_PORT="${SSH_PORT:-22}"

SSH_OPTS=( -o StrictHostKeyChecking=accept-new -p "$SSH_PORT" )
if [[ -n "${SSH_KEY:-}" ]]; then
    SSH_OPTS+=( -i "$SSH_KEY" )
fi

SKIP_BUILD=false
for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD=true ;;
        -h|--help)
            sed -n '2,14p' "$0"
            exit 0
            ;;
    esac
done

if [[ "$SKIP_BUILD" != "true" ]]; then
    echo "==> Building Astro site (npm run build)..."
    npm run build
else
    echo "==> Skipping build (using existing dist/)"
fi

if [[ ! -d "dist" ]]; then
    echo "ERROR: dist/ not found. Run 'npm run build' first, or omit --skip-build."
    exit 1
fi

# Quick sanity checks on the build output
PAGES=$(find dist -name "index.html" | wc -l)
echo "==> Built $PAGES index.html pages"
if [[ "$PAGES" -lt 100 ]]; then
    echo "WARNING: page count unusually low. Expected ≥400 (113 articles + 180 recitals + history + ...)"
    read -r -p "Continue deployment? [y/N] " yn
    [[ "$yn" == "y" || "$yn" == "Y" ]] || exit 1
fi

echo "==> Deploying to ${VPS_USER}@${VPS_HOST}:${VPS_PATH}"

# rsync options:
#   -a : archive mode (preserve attributes, symlinks, etc.)
#   -z : compress during transfer
#   -v : verbose
#   --delete : remove files on remote that aren't in source (clean cutover)
#   --exclude : protect .well-known/ on the remote (Caddy ACME challenges) if it ever lives there
rsync -avz \
    --delete \
    --exclude='.well-known' \
    -e "ssh ${SSH_OPTS[*]}" \
    "dist/" "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/"

echo "==> Deployment complete."
echo "    Live: https://aiact.annotated.nl/ (once DNS is cut over)"
echo ""
echo "    Verify on the VPS:"
echo "      ssh ${VPS_USER}@${VPS_HOST} 'ls -la ${VPS_PATH}/'"
echo "      ssh ${VPS_USER}@${VPS_HOST} 'sudo caddy validate --config /etc/caddy/Caddyfile'"
