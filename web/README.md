# My Life — Web console

A Vite + React + TypeScript + Tailwind console for manually exercising the My Life
API. It talks only to the public HTTP API.

## Run it locally

**1. Start the backend** (from the repo root):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn mylife.main:app --reload      # http://127.0.0.1:8000  (docs at /docs)
```

**2. Start the web app** (from `web/`):

```bash
npm install
npm run dev                           # http://127.0.0.1:5173
```

In dev, the Vite proxy (`vite.config.ts`) forwards API paths (`/auth`, `/finance`,
`/goals`, …) to the backend, so the browser talks to it **same-origin** — no CORS
config needed. Point the proxy elsewhere with `VITE_API_TARGET`. For a non-proxied
build, set `VITE_API_BASE_URL` to the API's URL (see `.env.example`).

**3. Sign in.** Create a user first (via the API `POST /users`, or the interactive
docs at `http://127.0.0.1:8000/docs`), then log in on the web app. Use the sidebar
to reach each feature area.

## Scripts

| Script | What it does |
| ------ | ------------ |
| `npm run dev` | Vite dev server (with the API proxy) |
| `npm run build` | Type-check + production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint |
| `npm run test` | Vitest (jsdom + Testing Library) |

The CI `web` job runs typecheck + lint + test on every push.
