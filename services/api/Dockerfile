FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY services/api/pyproject.toml services/api/uv.lock ./

# Install dependencies (frozen lockfile)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY services/api/src/ src/
COPY services/api/alembic.ini alembic.ini
COPY services/api/alembic/ alembic/

# Copy scripts and data (accessible from api container)
COPY scripts/ scripts/
COPY data/ data/

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
