#!/usr/bin/env bash
# Pull the latest main, rebuild the static site, refresh the nginx snippets, reload nginx and restart the MCP/API
# backend if it is installed (deploy/setup-server.sh). Safe to re-run.
set -euo pipefail
DIR=${DIR:-/var/www/contractradar-testset}
REPO=${REPO:-https://github.com/Marxist-Leninist/contractradar-testset.git}
VENV=${VENV:-/opt/contractradar-mcp/venv}
if [ ! -d "$DIR/.git" ]; then
  git clone "$REPO" "$DIR"
fi
cd "$DIR"
git fetch --quiet origin main
git reset --hard --quiet origin/main
python3 -m crtest.site --cases cases --results results --out site/dist
install -m 0644 deploy/nginx-contractradar-ratelimit.conf /etc/nginx/conf.d/contractradar-ratelimit.conf
install -D -m 0644 deploy/nginx-contractradar-locations.conf /etc/nginx/snippets/contractradar-locations.conf
if [ ! -e /etc/nginx/sites-enabled/contractradar ]; then
  cp deploy/nginx-contractradar.conf /etc/nginx/sites-available/contractradar
  ln -s /etc/nginx/sites-available/contractradar /etc/nginx/sites-enabled/contractradar
fi
nginx -t || { echo "nginx -t failed; nothing reloaded" >&2; exit 1; }
systemctl reload nginx
if [ -f /etc/systemd/system/contractradar-mcp.service ]; then
  "$VENV/bin/pip" install --quiet -r requirements-server.txt || echo "warning: could not refresh the backend's dependencies" >&2
  systemctl restart contractradar-mcp.service
  ok=""
  for i in $(seq 1 20); do
    if curl -fsS -m 2 http://127.0.0.1:8765/api/health >/dev/null 2>&1; then ok=1; break; fi
    sleep 1
  done
  [ -n "$ok" ] || { echo "contractradar-mcp did not come back; see journalctl -u contractradar-mcp" >&2; exit 1; }
fi
echo "deployed $(git rev-parse --short HEAD) at $(date -u +%FT%TZ)"
