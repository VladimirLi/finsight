# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────
# Stage 1: dependency builder
# ──────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build-only system deps (gcc, etc.) — not copied to final image
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create the virtualenv at its FINAL runtime path (/app/venv) so the console
# scripts' shebangs (e.g. alembic, uvicorn) resolve after being copied to the
# runtime stage. Building it under /build would hardcode a path that no longer
# exists at runtime ("cannot execute: required file not found").
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ──────────────────────────────────────────────
# Stage 2: runtime image
# ──────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --gid 1001 appgroup \
 && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtualenv from builder (same path → shebangs stay valid)
COPY --from=builder /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy application source + Alembic migrations (production schema path)
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./alembic.ini
COPY --chown=appuser:appgroup scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
RUN chmod +x ./scripts/docker-entrypoint.sh

# Uploads directory (overridden by volume mount in compose)
RUN mkdir -p /app/uploads && chown appuser:appgroup /app/uploads

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Production path: run `alembic upgrade head` then launch uvicorn.
CMD ["./scripts/docker-entrypoint.sh"]
