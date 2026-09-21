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
#
# `< /dev/null` matters: this whole script is streamed to `bash -s` over SSH
# with its source as bash's own stdin (see deploy.yml's "Deploy over SSH"
# step). `docker compose run` attaches to stdin by default like `docker run
# -i`, and without this redirect it inherits that same fd — reading (and so
# silently discarding) every line still unread from THIS SCRIPT, including
# everything below this point. Root-caused live: the deploy job reported
# success with zero log output for anything after migrate, because `up -d`
# and everything after it was being consumed as migrate's stdin instead of
# ever reaching bash as commands.
compose run --rm migrate < /dev/null

# Roll the stack to the new image. --force-recreate is belt-and-suspenders:
# api/worker should already be recreated by a plain `up -d` since the pulled
# image differs, but this guarantees it regardless.
compose up -d
compose up -d --force-recreate api worker

# Reclaim disk from superseded image layers.
docker image prune -f

echo "Deploy complete."
