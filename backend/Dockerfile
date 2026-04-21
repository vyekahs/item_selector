# syntax=docker/dockerfile:1.6
# ---- Stage 1: builder (install dependencies with uv) ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# uv for fast resolution/install
RUN pip install --no-cache-dir uv==0.5.14

WORKDIR /app

# Only copy dependency manifest first for better layer caching
COPY pyproject.toml ./

# Resolve + install into a local venv at /app/.venv
RUN uv venv /app/.venv \
    && . /app/.venv/bin/activate \
    && uv pip install --no-cache-dir -e .

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

# curl is used by the HEALTHCHECK
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the prebuilt virtualenv from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source (includes data/ with seed xlsx/xls files and
# docker-entrypoint.sh which runs migrations + data bootstrap on start).
COPY . /app

RUN chmod +x /app/docker-entrypoint.sh

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# start-period is generous: first boot imports ~21MB customs xlsx which
# can take 60–90s before /health responds.
HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=10 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
