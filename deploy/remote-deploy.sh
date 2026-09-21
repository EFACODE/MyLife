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

cd "$DIR"

# Compose reads ${MYLIFE_DOMAIN}/${POSTGRES_PASSWORD}/etc. from --env-file (the
# `env_file:` service directive only injects vars into containers, not into
# compose-level interpolation), so pass .env.prod on every invocation.
compose() { docker compose --env-file .env.prod -f docker-compose.prod.yml "$@"; }

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
compose pull

# Apply migrations (one-shot) before starting the new app/worker.
compose run --rm migrate

# Roll the stack to the new image. In the non-interactive shell this script
# runs under over SSH, Compose's own "has the resolved image changed?" check
# has been observed to silently keep the old api/worker containers running
# even though the correct :$MYLIFE_IMAGE was freshly pulled above (confirmed:
# the identical pull -> run migrate -> up -d sequence, run by hand in an
# interactive shell, recreates them correctly every time) — force it instead
# of relying on that heuristic, so a deploy always actually applies.
compose up -d
compose up -d --force-recreate api worker

# Reclaim disk from superseded image layers.
docker image prune -f

echo "Deploy complete."
