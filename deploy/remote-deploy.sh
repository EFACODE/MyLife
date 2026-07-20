#!/usr/bin/env bash
# Remote deploy script — runs ON the VPS, streamed over SSH by the Deploy
# workflow (.github/workflows/deploy.yml). It pulls the freshly published image,
# applies migrations and restarts the Compose stack. See DEPLOY.md / cicd.md.
#
# Required env (passed by the workflow): MYLIFE_IMAGE=ghcr.io/<owner>/<repo>:<sha>
# Optional env:
#   MYLIFE_DIR   deploy directory holding docker-compose.prod.yml (default ~/mylife)
#   GHCR_USER / GHCR_TOKEN   only needed if the GHCR package is private
set -euo pipefail

: "${MYLIFE_IMAGE:?MYLIFE_IMAGE must be set (image ref to deploy)}"
DIR="${MYLIFE_DIR:-$HOME/mylife}"
COMPOSE_FILE="docker-compose.prod.yml"

cd "$DIR"

# Refresh the compose file / Caddyfile from the repo (fast-forward only).
if [ -d .git ]; then
  git pull --ff-only
fi

# Authenticate to GHCR only if the package is private.
if [ -n "${GHCR_TOKEN:-}" ]; then
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:?GHCR_USER required with GHCR_TOKEN}" --password-stdin
fi

export MYLIFE_IMAGE
echo "Deploying image: $MYLIFE_IMAGE"

# Pull the new image for every service that uses it.
docker compose -f "$COMPOSE_FILE" pull

# Apply migrations (one-shot) before starting the new app/worker.
docker compose -f "$COMPOSE_FILE" run --rm migrate

# Roll the stack to the new image.
docker compose -f "$COMPOSE_FILE" up -d

# Reclaim disk from superseded image layers.
docker image prune -f

echo "Deploy complete."
