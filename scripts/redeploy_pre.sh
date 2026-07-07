#!/usr/bin/env bash
# Redeploy PRE (dp-pre-bot) with RAG_MIN_SCORE=0.50 + KB reindex.
# Run from the repo root on the VPS:  bash scripts/redeploy_pre.sh
# PRE is a single shared environment — both feature/pre_gadea and
# feature/dev_alvaro auto-deploy here via CI, whichever pushes last wins.
# Override the branch manually with:  BRANCH=feature/dev_alvaro bash scripts/redeploy_pre.sh
# See docs/deploy-pre-redeploy.md for the manual step-by-step and rollback.
set -euo pipefail

BRANCH="${BRANCH:-feature/pre_gadea}"
COMPOSE="docker-compose.vps.yml"
BOT="dp-pre-bot"
DB="dp-pre-postgres"
ENV_FILE=".env.pre"

echo "==> 1/5 Updating code to $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"
git log --oneline -1

echo "==> 2/5 Setting RAG_MIN_SCORE=0.50 in $ENV_FILE"
if [ -f "$ENV_FILE" ]; then
  if grep -q '^RAG_MIN_SCORE=' "$ENV_FILE"; then
    sed -i 's/^RAG_MIN_SCORE=.*/RAG_MIN_SCORE=0.50/' "$ENV_FILE"
  else
    echo 'RAG_MIN_SCORE=0.50' >> "$ENV_FILE"
  fi
  grep '^RAG_MIN_SCORE=' "$ENV_FILE"
else
  echo "WARNING: $ENV_FILE not found — set RAG_MIN_SCORE=0.50 manually." >&2
fi

echo "==> 3/5 Rebuilding & restarting $BOT"
docker compose -f "$COMPOSE" up -d --build "$BOT"
sleep 5
docker compose -f "$COMPOSE" logs --tail=20 "$BOT" || true

echo "==> 4/5 Reindexing KB inside $BOT (uses PRE DB + OpenAI from $ENV_FILE)"
docker compose -f "$COMPOSE" exec -T "$BOT" python -m scripts.load_embeddings --yes

echo "==> 5/5 Verifying"
docker compose -f "$COMPOSE" exec -T "$BOT" \
  python -c "import urllib.request; print('health:', urllib.request.urlopen('http://localhost:8000/health').read())" || true
docker compose -f "$COMPOSE" exec -T "$DB" \
  psql -U postgres -d diving_planet -c "SELECT count(*) AS kb_documents FROM kb_documents;" || true

echo "==> Done. Test in the PRE Chatwoot widget (see docs/deploy-pre-redeploy.md §5)."
