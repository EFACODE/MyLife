# My Life

[![CI](https://github.com/EFACODE/MyLife/actions/workflows/ci.yml/badge.svg)](https://github.com/EFACODE/MyLife/actions/workflows/ci.yml)

Event-sourced personal life platform. The organizing principle is simple:
**everything is a Life Event**. Every domain (Finance, Health, Timeline, …)
publishes immutable events into a shared kernel, and features are built by
reading and reacting to that stream.

This repository is being built incrementally against the technical backlog
(`myLife-indice-tarefas.md`). Each task maps to one small, spec-traceable PR.

> **Status:** Phase 0 — repository foundation. No business logic yet.

## Stack

- **Python 3.11+**
- **FastAPI** — HTTP API
- **Pydantic v2** / **pydantic-settings** — models & configuration
- **SQLAlchemy 2.0** — persistence
- **ruff** (lint + format), **mypy** (types), **pytest** (tests), **pre-commit**

## Project layout

```
src/mylife/
  main.py          # FastAPI app factory + ASGI entrypoint
  core/config.py   # settings (env-driven, local defaults)
  api/health.py    # liveness endpoint (proves the shell boots)
  db/base.py       # generic SQLAlchemy base / engine / session (no models yet)
tests/             # pytest suite
specs/             # feature & domain specifications (written before code)
```

## Getting started

Create a virtual environment and install the project with its dev extras:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Install the git hooks:

```bash
pre-commit install
```

## Local services (Docker Compose)

The backing services (Postgres and Redis) run via Docker Compose. Copy the
example environment file and start them:

```bash
cp .env.example .env
docker compose up -d
docker compose ps        # check that both services are healthy
```

Once `.env` exists, the application reads its `MYLIFE_`-prefixed variables and
connects to the Postgres/Redis instances above. Stop the services with
`docker compose down` (add `-v` to also remove the data volumes).

## Development commands

| Task              | Command                          |
| ----------------- | -------------------------------- |
| Run the API       | `uvicorn mylife.main:app --reload` |
| Run a worker      | `celery -A mylife.workers.celery_app:celery_app worker` |
| Lint              | `ruff check .`                   |
| Format            | `ruff format .`                  |
| Type-check        | `mypy`                           |
| Test              | `pytest`                         |
| Migrate DB        | `alembic upgrade head`           |
| New migration     | `alembic revision -m "…" --autogenerate` |
| All pre-commit    | `pre-commit run --all-files`     |

Once running, the API docs are served at `http://localhost:8000/docs` and the
liveness probe at `http://localhost:8000/health`.

## Configuration

Settings are read from environment variables prefixed with `MYLIFE_` (and an
optional `.env` file). Every value has a local-development default, so the app
boots with zero configuration. Key variables:

| Variable             | Default                        | Description                |
| -------------------- | ------------------------------ | -------------------------- |
| `MYLIFE_ENVIRONMENT` | `local`                        | Deployment environment     |
| `MYLIFE_DEBUG`       | `false`                        | FastAPI debug mode         |
| `MYLIFE_DATABASE_URL`| `sqlite:///./mylife.sqlite3`   | SQLAlchemy database URL     |
| `MYLIFE_REDIS_URL`   | `redis://localhost:6379/0`     | Redis connection URL       |
