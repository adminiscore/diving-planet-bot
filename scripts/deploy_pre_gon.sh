#!/usr/bin/env bash
# Deploy the current feature/pruebaGon state to the shared PRE environment.
#
# Run from your LOCAL repo root:
#     bash scripts/deploy_pre_gon.sh
#
# What it does: pushes your integration branch (feature/pruebaGon) and then
# updates the mirror branch (feature/pre_pruebaGon), which triggers the
# `deploy-pre` GitHub Action (rebuild dp-pre-bot + reindex KB + health check).
#
# It does NOT run on every commit — only when you run this — so a routine commit
# doesn't rebuild PRE. See docs/deploy-pre-redeploy.md.
#
# Options (env vars):
#     DEV_BRANCH=feature/pruebaGon      your integration branch (source of truth)
#     PRE_BRANCH=feature/pre_pruebaGon  your PRE mirror (the deploy trigger)
#     SKIP_LINT=1                       skip the local `ruff check src` pre-check
#     YES=1                             don't ask for confirmation (CI/non-interactive)
set -euo pipefail

DEV_BRANCH="${DEV_BRANCH:-feature/pruebaGon}"
PRE_BRANCH="${PRE_BRANCH:-feature/pre_pruebaGon}"
REMOTE="${REMOTE:-origin}"

cd "$(git rev-parse --show-toplevel)"

# 1) Safety: warn about uncommitted work — the deploy uses the COMMITTED state,
#    not your working tree. Anything not committed won't reach PRE.
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  Tienes cambios sin commitear. El deploy usa lo COMMITEADO, no tu working tree." >&2
  echo "    Commitea primero si quieres que esos cambios lleguen a PRE." >&2
fi

# 2) Local lint pre-check (CI enforces this; fail fast before triggering a deploy).
if [ "${SKIP_LINT:-0}" != "1" ]; then
  if command -v ruff >/dev/null 2>&1; then
    echo "==> ruff check src"
    ruff check src
  else
    echo "    (ruff no instalado; me lo salto — el CI igual lo corre)" >&2
  fi
fi

# 3) Confirm — PRE is a SINGLE shared environment (Gadea / Álvaro / tú).
CURRENT_HEAD="$(git rev-parse --short HEAD)"
echo
echo "Vas a desplegar '$DEV_BRANCH' ($CURRENT_HEAD) a la PRE COMPARTIDA vía '$PRE_BRANCH'."
echo "Esto sobreescribe lo que haya desplegado ahora mismo (avisa al equipo)."
if [ "${YES:-0}" != "1" ]; then
  read -r -p "¿Continuar? [y/N] " ans
  case "$ans" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Cancelado."; exit 1 ;;
  esac
fi

# 4) Push your integration branch, then update the mirror to trigger the deploy.
echo "==> Pushing $DEV_BRANCH"
git push "$REMOTE" "$DEV_BRANCH"

echo "==> Updating mirror $PRE_BRANCH -> triggers deploy-pre"
git push "$REMOTE" "$DEV_BRANCH:$PRE_BRANCH" --force-with-lease

echo
echo "✅ Listo. La Action 'CI' del branch $PRE_BRANCH corre Lint+Tests y luego 'Deploy to PRE'."
echo "   Míralo en la pestaña Actions de GitHub (adminiscore/diving-planet-bot)."
