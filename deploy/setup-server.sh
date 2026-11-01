#!/usr/bin/env bash
# One-time (idempotent) setup of the MCP + HTTP submission backend on the web host. Run as root after deploy.sh has
# cloned the repo. On a host whose vhost certbot already manages, replace the location blocks in its TLS server block
# with: include /etc/nginx/snippets/contractradar-locations.conf;   (deploy.sh installs and refreshes that snippet).
set -euo pipefail
DIR=${DIR:-/var/www/contractradar-testset}
VENV=${VENV:-/opt/contractradar-mcp/venv}
STATE=/var/lib/contractradar
id contractradar >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --no-create-home --shell /usr/sbin/nologin contractradar
install -d -o contractradar -g contractradar -m 0750 "$STATE" "$STATE/submissions"
[ -x "$VENV/bin/pip" ] || python3 -m venv --clear "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$DIR/requirements-server.txt"
install -m 0644 "$DIR/deploy/nginx-contractradar-ratelimit.conf" /etc/nginx/conf.d/contractradar-ratelimit.conf
install -D -m 0644 "$DIR/deploy/nginx-contractradar-locations.conf" /etc/nginx/snippets/contractradar-locations.conf
install -m 0644 "$DIR/deploy/contractradar-mcp.service" /etc/systemd/system/contractradar-mcp.service
systemctl daemon-reload
systemctl enable contractradar-mcp.service
systemctl restart contractradar-mcp.service
ok=""
for i in $(seq 1 20); do
  if curl -fsS -m 2 http://127.0.0.1:8765/api/health; then echo; ok=1; break; fi
  sleep 1
done
[ -n "$ok" ] || { echo "contractradar-mcp did not come up; see journalctl -u contractradar-mcp" >&2; exit 1; }
echo "backend: $(systemctl is-active contractradar-mcp.service)"
