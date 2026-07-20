# Spec: Platform — CI/CD build, publish & deploy (`T12`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T12.1`–`T12.2` (platform)
- **Bounded context:** Platform (delivery / deployment automation)
- **Author / date:** Claude Code / 2026-07-20
- **Depends on:** `T11` (Dockerfile, production compose, DEPLOY.md)

## 1. Purpose & business context

Make releases **hands-off**. Today a human must build the image and run the
Compose bring-up on the VPS. This task adds a GitHub Actions pipeline that, on
every push to `main`, **builds the Docker image and publishes it to the GitHub
Container Registry (GHCR)**, then — when VPS SSH secrets are configured —
**deploys it to the host automatically** (pull the new image, run migrations,
restart the stack). No new infrastructure is required to publish the image (GHCR
uses the built-in `GITHUB_TOKEN`); the only one-time human setup is providing the
VPS SSH secrets.

## 2. Scope

- **In scope:**
  - `T12.1` — **Build & publish**: a `Deploy` workflow job that builds the
    existing multi-stage `Dockerfile` and pushes `:latest` + `:<sha>` tags to
    `ghcr.io/<owner>/<repo>` (lowercased), with layer caching. Parameterize the
    production compose image via `MYLIFE_IMAGE` (default GHCR) so the server can
    **pull** instead of building.
  - `T12.2` — **Auto-deploy**: a gated `deploy` job that, only when `VPS_HOST` /
    `VPS_USER` / `VPS_SSH_KEY` secrets are present, SSHes to the host and runs a
    `deploy/remote-deploy.sh` script (`git pull` compose, `docker compose pull`,
    one-shot migrate, `up -d`, prune). DEPLOY.md documents the 3 secrets and GHCR
    package visibility.
- **Out of scope:** provisioning the VPS itself (the user's cloud account);
  buying a domain; blue/green or multi-host rollout; an S3 blob adapter;
  publishing to Docker Hub.

## 3. User stories & acceptance criteria

- As an **operator**, pushing to `main` publishes a runnable image with no manual
  build.
  - **AC1:** On push to `main`, the `build` job logs in to GHCR with the built-in
    token and pushes `ghcr.io/<owner>/<repo>:latest` and `:<sha>`.
  - **AC2:** The image name is lowercased (GHCR requirement) even though the repo
    slug is mixed-case.
- As an **operator with a VPS**, pushing to `main` deploys automatically.
  - **AC3:** When `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY` are set, the `deploy` job
    connects over SSH and runs the remote script that pulls the new image, applies
    migrations and restarts the stack.
  - **AC4:** When those secrets are **absent**, the `deploy` job **skips** cleanly
    (emits a notice, does not fail the pipeline) — so the pipeline is safe to merge
    before any VPS exists.
- As an **operator**, the same compose file works for both build-on-server and
  pull-from-registry.
  - **AC5:** `docker compose -f docker-compose.prod.yml config` stays valid;
    `MYLIFE_IMAGE` defaults to the GHCR image and is overridable.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `.github/workflows/deploy.yml`: on `push` to `main` + `workflow_dispatch`. `build` job with `permissions: packages: write`, `docker/login-action` (registry `ghcr.io`, user `github.actor`, pass `GITHUB_TOKEN`), `docker/build-push-action` pushing `:latest` + `:<sha>` with `type=gha` cache. Image ref lowercased from `github.repository`. |
| FR-2 | Functional | `docker-compose.prod.yml`: `migrate`/`api`/`worker` use `image: ${MYLIFE_IMAGE:-ghcr.io/efacode/mylife:latest}`; `api` keeps `build: .` so a from-source bring-up still works. |
| FR-3 | Functional | `deploy` job `needs: build`, gated on presence of `VPS_HOST`+`VPS_SSH_KEY` (computed to a step output; absent → skip with a notice, pipeline stays green). Writes the key, `ssh-keyscan` the host, runs `deploy/remote-deploy.sh` over SSH passing `MYLIFE_IMAGE=…:<sha>`. |
| FR-4 | Functional | `deploy/remote-deploy.sh`: `set -euo pipefail`; `cd` to the deploy dir (`MYLIFE_DIR`, default `~/mylife`); `git pull --ff-only`; optional GHCR login if `GHCR_TOKEN` set; `docker compose -f docker-compose.prod.yml pull`; run `migrate` one-shot; `up -d`; `docker image prune -f`. |
| NFR-1 | Security | **No secrets in the repo.** VPS host/user/key and any GHCR token come only from GitHub Actions secrets, masked in logs. The SSH key is written to a mode-0600 file on the ephemeral runner. Host key pinned via `ssh-keyscan`. `MYLIFE_JWT_SECRET`/DB password stay in the server's `.env.prod` (never in CI). |
| NFR-2 | Reliability | The pipeline must not fail when no VPS is configured (AC4). Deploy concurrency is serialized (`cancel-in-progress: false`) so two pushes can't race a host. |
| NFR-3 | Quality | Workflow YAML parses; existing `ruff`/`mypy`/`pytest`/web gates unaffected (no app-code change); compose `config` valid. |

## 5. API & event contracts

- None. This is delivery tooling — no HTTP endpoints, no events, no migration.

## 6. Data model & migration strategy

- **No schema change.** Migrations are still applied by the one-shot `migrate`
  service (`alembic upgrade head`) — now invoked by the remote deploy script on
  each release, consistent with the append-only, forward-only history invariant.
- New files: `.github/workflows/deploy.yml`, `deploy/remote-deploy.sh`. Edits:
  `docker-compose.prod.yml` (image parameterization), `DEPLOY.md` (CI/CD section).

## 7. Privacy, consent, access-control & retention

- The published image contains only the app + built SPA — no user data, no
  secrets. GHCR package visibility is the operator's choice (public → no
  server-side auth; private → a read-only `GHCR_TOKEN`). No personal data flows
  through CI.

## 8. Test plan

- **Workflow validity (NFR-3):** the YAML parses; job graph is `build → deploy`.
- **Publish (AC1/AC2):** verified when the workflow runs on `main` — image lands
  in GHCR under the lowercased name (real push happens post-merge).
- **Skip-safe (AC4):** with no VPS secrets, the `deploy` job's check step outputs
  `ready=false` and downstream steps are `if`-guarded off → pipeline green.
- **Compose (AC5):** `docker compose -f docker-compose.prod.yml config` valid with
  `MYLIFE_IMAGE` defaulted and overridden.

## 9. Dependencies, open decisions, risks & future work

- **Open decisions (resolved):**
  - *Registry = GHCR.* → no extra account/secret to publish (built-in token).
  - *Deploy transport = SSH + Compose.* → matches T11 topology B exactly; the
    server pulls the pre-built image instead of building.
  - *Deploy is secret-gated & skip-safe.* → the pipeline is mergeable before a VPS
    exists; enabling deploy is purely "add 3 secrets".
- **Risks:** a private GHCR package needs the host to authenticate — mitigated by
  documenting public visibility or a read-only token; `ssh-keyscan` TOFU pins the
  host key on first run (document verifying the fingerprint).
- **Future work:** environment protection rules / manual approval before deploy;
  image vulnerability scanning; staging environment; rollback to a previous `:<sha>`.

## 10. Definition of Done

- [ ] Spec approved; implementation traceable.
- [ ] `deploy.yml` builds & pushes to GHCR (lowercased, `:latest`+`:<sha>`, cached).
- [ ] Compose image parameterized (`MYLIFE_IMAGE`), `config` valid.
- [ ] `deploy` job SSH-deploys when secrets present, skips cleanly otherwise.
- [ ] `deploy/remote-deploy.sh` pulls, migrates, restarts, prunes.
- [ ] DEPLOY.md documents the secrets + GHCR visibility; backlog + spec updated.
