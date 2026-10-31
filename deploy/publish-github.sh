#!/usr/bin/env bash
# Create the public GitHub repo and push. Run from the repo root on a machine where `gh auth status` shows Marxist-Leninist.
set -euo pipefail
REPO=${REPO:-Marxist-Leninist/contractradar-testset}
export HOME=${HOME:-/root}
git rev-parse --is-inside-work-tree >/dev/null
if gh repo view "$REPO" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$REPO.git"
  git push -u origin main
else
  gh repo create "$REPO" --public --source . --remote origin --push \
    --description "Synthetic UK council contract documents with gold labels, hazards and Procurement Act 2023 flags for scoring AI extraction (ContractRadar pilot)"
fi
gh repo edit "$REPO" --add-topic procurement --add-topic uk-public-sector --add-topic document-extraction --add-topic benchmark --homepage https://contractradar.opentransformers.online || true
echo "https://github.com/$REPO"
