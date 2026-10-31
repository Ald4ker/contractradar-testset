#!/usr/bin/env bash
# One-shot: create the DNS record on Cloudflare, get a Let's Encrypt cert, then (optionally) turn the orange cloud on.
# Run on the web host (communist-web) as root. Needs an env file with the Cloudflare credentials, never committed:
#   CF_EMAIL=...   CF_KEY=...   CF_ZONE=<zone id for opentransformers.online>
# Usage: CF_ENV=/root/.cf-contractradar.env ./deploy/publish-dns-tls.sh [--proxy]
set -euo pipefail
HOST=${HOST:-contractradar.opentransformers.online}
SUB=${SUB:-contractradar}
ORIGIN_IP=${ORIGIN_IP:-46.62.174.233}
EMAIL=${EMAIL:-Scottbisset1@hotmail.com}
CF_ENV=${CF_ENV:-/root/.cf-contractradar.env}
set -a; . "$CF_ENV"; set +a
API=https://api.cloudflare.com/client/v4
auth=(-H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_KEY" -H "Content-Type: application/json")

echo "== zone SSL mode (must be full/strict for the orange cloud; flexible would loop with the HTTPS redirect)"
mode=$(curl -s "${auth[@]}" "$API/zones/$CF_ZONE/settings/ssl" | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["value"])')
echo "ssl mode: $mode"

echo "== DNS record"
rid=$(curl -s "${auth[@]}" "$API/zones/$CF_ZONE/dns_records?name=$HOST" | python3 -c 'import sys,json; r=json.load(sys.stdin)["result"]; print(r[0]["id"] if r else "")')
if [ -z "$rid" ]; then
  rid=$(curl -s -X POST "${auth[@]}" "$API/zones/$CF_ZONE/dns_records" \
    -d "{\"type\":\"A\",\"name\":\"$SUB\",\"content\":\"$ORIGIN_IP\",\"ttl\":300,\"proxied\":false,\"comment\":\"ContractRadar test set site\"}" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["success"], d; print(d["result"]["id"])')
  echo "created record $rid (DNS-only for the ACME challenge)"
else
  echo "record exists: $rid"
fi
for i in $(seq 1 30); do getent hosts "$HOST" >/dev/null && break; sleep 5; done
getent hosts "$HOST" || { echo "still not resolving; try again in a minute"; exit 1; }

echo "== certificate"
certbot --nginx -d "$HOST" --non-interactive --agree-tos -m "$EMAIL" --redirect
nginx -t && systemctl reload nginx
curl -s -o /dev/null -w "https://$HOST/ -> %{http_code}\n" "https://$HOST/"

if [ "${1:-}" = "--proxy" ]; then
  if [ "$mode" = "flexible" ]; then
    echo "zone SSL mode is flexible: leaving the record DNS-only to avoid a redirect loop. Set the zone to Full (strict) first."
  else
    curl -s -X PATCH "${auth[@]}" "$API/zones/$CF_ZONE/dns_records/$rid" -d '{"proxied":true}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print("proxied:", d["success"])'
  fi
fi
echo "done"
