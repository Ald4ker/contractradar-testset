#!/usr/bin/env bash
# Pull the latest main, rebuild the static site, reload nginx. Safe to re-run.
set -euo pipefail
DIR=${DIR:-/var/www/contractradar-testset}
REPO=${REPO:-https://github.com/Marxist-Leninist/contractradar-testset.git}
if [ ! -d "$DIR/.git" ]; then
  git clone "$REPO" "$DIR"
fi
cd "$DIR"
git fetch --quiet origin main
git reset --hard --quiet origin/main
python3 -m crtest.site --cases cases --results results --out site/dist
if [ ! -e /etc/nginx/sites-enabled/contractradar ]; then
  cp deploy/nginx-contractradar.conf /etc/nginx/sites-available/contractradar
  ln -s /etc/nginx/sites-available/contractradar /etc/nginx/sites-enabled/contractradar
fi
nginx -t && systemctl reload nginx
echo "deployed $(git rev-parse --short HEAD) at $(date -u +%FT%TZ)"
