# Deploying My Life (single VPS + Docker Compose)

This is the operational runbook for the **topology B** deployment described in
[`specs/domain/platform/deployment.md`](./specs/domain/platform/deployment.md):
one host runs the whole stack via Docker Compose. The FastAPI app serves the
built SPA **same-origin** (no CORS), and Caddy terminates TLS and proxies the
domain to it.

```
            ┌──────────────────────── VPS ────────────────────────┐
 Internet ──┤ caddy :80/:443 ── api :8000 ── postgres :5432        │
   (443)    │   (TLS, domain)   (FastAPI + SPA)   redis :6379      │
            │                    worker (celery)                   │
            └──────────────────────────────────────────────────────┘
```

Services: `postgres`, `redis`, `migrate` (one-shot `alembic upgrade head`),
`api`, `worker`, `caddy`. State lives in named volumes (`postgres_data`,
`redis_data`, `blob_data`, `caddy_data`, `caddy_config`).

---

## 1. Prerequisites

- A VPS (Hostinger, Hetzner, DigitalOcean, …). **2 vCPU / 4 GB RAM / 40 GB
  disk** is a comfortable starting point; 1 GB is too little for Postgres +
  the build.
- A registered **domain** (or subdomain) you control.
- SSH access to the host as a sudo-capable user.

## 2. Provision the host

Install Docker Engine + the Compose plugin (Debian/Ubuntu):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out/in so the group applies
docker compose version            # confirm the v2 plugin is present
```

Open the firewall for HTTP/HTTPS (and SSH). With `ufw`:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

> Do **not** expose Postgres (5432) or Redis (6379) publicly — they stay on the
> internal Compose network and must not be published.

## 3. Point DNS at the host

Create an **A record** for your domain pointing at the VPS's public IPv4 (and an
`AAAA` record if you have IPv6). Caddy obtains a Let's Encrypt certificate
automatically on first start, so DNS must resolve **before** you bring the stack
up. Verify:

```bash
dig +short mylife.example.com    # should print the VPS IP
```

## 4. Get the code and configure secrets

```bash
git clone https://github.com/efacode/mylife.git
cd mylife
cp .env.prod.example .env.prod
```

Edit `.env.prod`:

| Variable | What to set |
| --- | --- |
| `MYLIFE_DOMAIN` | Your domain, e.g. `mylife.example.com` (Caddy issues TLS for it). |
| `POSTGRES_USER` / `POSTGRES_DB` | Fine to leave as `mylife`. |
| `POSTGRES_PASSWORD` | A strong random password. |
| `MYLIFE_DATABASE_URL` | Must embed the same user/password/db: `postgresql+psycopg://mylife:<password>@postgres:5432/mylife`. |
| `MYLIFE_REDIS_URL` | Leave as `redis://redis:6379/0`. |
| `MYLIFE_ENVIRONMENT` | `production`. |
| `MYLIFE_JWT_SECRET` | **Generate a long random secret** (below). Must stay stable across restarts, or every existing session/token is invalidated. |

Generate the JWT secret and a DB password:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # MYLIFE_JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # POSTGRES_PASSWORD
```

> `.env.prod` holds real secrets and is **git-ignored** — never commit it. Keep
> a copy in your password manager; losing `MYLIFE_JWT_SECRET` logs everyone out.

Sanity-check the rendered config before starting anything:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config >/dev/null && echo OK
```

## 5. Bring the stack up

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This builds the image (web SPA → FastAPI runtime), starts Postgres/Redis, runs
`migrate` to `alembic upgrade head`, then starts `api`, `worker` and `caddy`.
Watch it settle:

```bash
docker compose -f docker-compose.prod.yml ps          # all healthy/running; migrate = Exited (0)
docker compose -f docker-compose.prod.yml logs -f api  # ctrl-c to stop tailing
```

Verify from your workstation:

```bash
curl -fsS https://mylife.example.com/health/ready      # {"status":"ready",...}
```

Then open `https://mylife.example.com/` — the SPA loads and can register the
first user.

## 6. Automatic deploys (CI/CD)

The `Deploy` workflow (`.github/workflows/deploy.yml`) builds the image and
publishes it to the **GitHub Container Registry (GHCR)** on every push to `main`,
then deploys it to this host over SSH — so after the one-time setup below you
never build or restart by hand. The build/publish step needs **no** external
account (it uses the built-in `GITHUB_TOKEN`); only the SSH deploy needs secrets.

**One-time setup:**

1. **Prepare the host** as in sections 2–5 (Docker installed, `.env.prod` filled,
   the repo cloned to `~/mylife` — the default deploy dir; override with a
   `MYLIFE_DIR` secret/env if you clone elsewhere). Do the first bring-up manually
   (section 5) so the stack and volumes exist.
2. **Create a deploy SSH key** and authorize it on the host:
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N ""      # on your machine
   ssh-copy-id -i deploy_key.pub user@your-host   # authorize the public key
   ```
3. **Add GitHub Actions secrets** (repo → Settings → Secrets and variables →
   Actions):
   | Secret | Value |
   | --- | --- |
   | `VPS_HOST` | The host's IP or domain. |
   | `VPS_USER` | The SSH user (the one that owns `~/mylife` and can run `docker`). |
   | `VPS_SSH_KEY` | The **private** key contents (`cat deploy_key`). |
4. **GHCR package visibility.** After the first successful publish, either make the
   `mylife` package **public** (GHCR → the package → Package settings → Change
   visibility) so the host pulls without auth, or keep it private and add
   `GHCR_USER` + `GHCR_TOKEN` (a read-only PAT) to the host's environment so
   `deploy/remote-deploy.sh` can `docker login`.

Until `VPS_HOST`/`VPS_SSH_KEY` exist the deploy job **skips cleanly** (the build
still publishes the image), so it's safe to merge before the host is ready.

Once set up, every push to `main` runs `deploy/remote-deploy.sh` on the host:
`git pull` (refresh compose) → `docker compose pull` → one-shot `migrate`
(`alembic upgrade head`) → `up -d` → prune. You can also trigger it manually from
the Actions tab (**Run workflow**).

## 7. Day-2 operations

**Manual upgrade** (if you're not using CI/CD, or to build from source on the host):

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`migrate` re-runs `alembic upgrade head`, so schema changes apply before the new
`api`/`worker` start. Migrations are append-only and forward-only (consistent with
the project's immutable-history invariant). The compose `image` defaults to the
GHCR image but is overridden to a from-source build when you pass `--build`.

**Back up** (Postgres is the source of truth; blobs are the uploaded documents):

```bash
# Database → timestamped SQL dump
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U mylife mylife | gzip > backup-db-$(date +%F).sql.gz

# Document blob store
docker run --rm -v mylife_blob_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/backup-blobs-$(date +%F).tar.gz -C /data .
```

Store backups off-host and automate them with `cron`. Test a restore
periodically.

**Restore the database** into a fresh volume:

```bash
gunzip -c backup-db-YYYY-MM-DD.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U mylife -d mylife
```

**Rotate the JWT secret** (invalidates all existing tokens — users re-login):
edit `MYLIFE_JWT_SECRET` in `.env.prod`, then
`docker compose -f docker-compose.prod.yml up -d api worker`.

**Common checks:**

```bash
docker compose -f docker-compose.prod.yml logs migrate   # why a migration failed
curl -fsS https://mylife.example.com/metrics             # Prometheus metrics (T9)
docker compose -f docker-compose.prod.yml down           # stop stack (keeps volumes)
docker compose -f docker-compose.prod.yml down -v        # DANGER: also deletes all data volumes
```

## 8. Notes & limitations

- **Same-origin SPA:** the API mounts the built bundle at `/` only when
  `MYLIFE_STATIC_DIR` points at it (set in the compose file). Dev/test runs
  leave it unset and use the Vite dev server, so there is no CORS surface in
  production.
- **Secrets** are injected via `env_file: .env.prod` and never baked into the
  image or committed.
- **Scaling:** this topology targets a single household/user on one host. Moving
  to multiple replicas would require externalizing sessions (already stateless
  JWT) and running Postgres/Redis as managed services — out of scope for T11.
- **TLS for local testing without a domain:** set `MYLIFE_DOMAIN=:80` in
  `.env.prod` to have Caddy serve plain HTTP on port 80.
