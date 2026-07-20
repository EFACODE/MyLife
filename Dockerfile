# Multi-stage image for My Life: build the web SPA, then run the FastAPI app which
# serves that SPA same-origin (no CORS needed). See specs/domain/platform/deployment.md.

# --- Stage 1: build the web SPA ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- Stage 2: Python runtime ---
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MYLIFE_STATIC_DIR=/app/static
WORKDIR /app

# Install the package (deps resolved from pyproject).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# Migrations (run at release time) + the built SPA served same-origin.
COPY alembic.ini ./
COPY migrations ./migrations
COPY --from=web /web/dist ./static

# Run as a non-root user.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "mylife.main:app", "--host", "0.0.0.0", "--port", "8000"]
