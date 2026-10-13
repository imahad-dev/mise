# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOSTNAME=0.0.0.0 \
    PYTHONPATH=/app

WORKDIR /app

# Pin uv version (exact version matching uv.lock revision 3)
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

# --- Base Dependencies ---
FROM base AS deps
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Test Stage (dev dependencies + test suite) ---
FROM deps AS test
RUN uv sync --frozen --group dev --no-install-project
COPY services/api/src/ src/
COPY services/api/tests/ tests/
COPY services/api/alembic.ini alembic.ini
COPY services/api/alembic/ alembic/
COPY scripts/ scripts/
COPY data/ data/
ENV PATH="/app/.venv/bin:$PATH"
CMD ["pytest", "-v"]

# --- Runtime Stage (production-ready, no sync at startup) ---
FROM base AS runner
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY services/api/src/ src/
COPY services/api/alembic.ini alembic.ini
COPY services/api/alembic/ alembic/
COPY scripts/ scripts/
COPY data/ data/

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
