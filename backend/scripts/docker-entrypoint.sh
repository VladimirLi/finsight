#!/usr/bin/env bash
# Production / docker-compose entrypoint.
#
# Unlike the dev/SQLite path (which uses Base.metadata.create_all via
# app.db.database.init_db), the production path applies schema changes through
# Alembic so migrations are versioned and reviewable. We run `alembic upgrade
# head` to bring the database to the latest revision, then start the API server.
set -euo pipefail

echo "[entrypoint] applying database migrations (alembic upgrade head)…"
alembic upgrade head

echo "[entrypoint] starting API server…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
