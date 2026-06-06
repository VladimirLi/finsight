#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Full-stack smoke test.
#
# Brings the whole stack up via docker-compose (postgres + backend + frontend),
# waits for every container to report healthy, then asserts that:
#   1. the backend health endpoint answers OK through the nginx /api proxy, and
#   2. the SPA shell is served by the frontend container.
# Tears the stack down (and removes volumes) on exit, pass or fail.
#
# No real LLM key is required: the pipeline is never invoked here — this proves
# the deployment topology (build, networking, migrations, proxy, static serve)
# is sound. Extraction is covered by the backend e2e + Playwright tiers.
#
# Usage: scripts/smoke.sh
# Env:
#   FRONTEND_PORT   host port the frontend is published on (default 3000)
#   SMOKE_TIMEOUT   seconds to wait for health before failing (default 180)
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-180}"
PROJECT="finsight_smoke"
BASE="http://localhost:${FRONTEND_PORT}"

# Deterministic, throwaway settings so the stack boots without real secrets.
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-smoke_test_pw}"
export LLM_PROVIDER="${LLM_PROVIDER:-ollama}"
export FRONTEND_PORT

compose() { docker compose -p "$PROJECT" "$@"; }

teardown() {
  echo "── tearing down ──"
  compose logs --no-color --tail=40 || true
  compose down -v --remove-orphans || true
}
trap teardown EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required for the smoke test but was not found on PATH." >&2
  exit 127
fi

echo "── building + starting the stack (project=${PROJECT}) ──"
# --wait blocks until every service with a healthcheck is healthy (or fails).
compose up --build -d --wait --wait-timeout "$SMOKE_TIMEOUT"

echo "── 1/2 backend health via the nginx /api proxy ──"
health="$(curl -fsS "${BASE}/api/health")"
echo "    ${health}"
echo "$health" | grep -q '"status":"ok"' || {
  echo "ERROR: /api/health did not report status ok" >&2
  exit 1
}

echo "── 2/2 SPA shell served by the frontend ──"
curl -fsS "${BASE}/" | grep -qiE '<div id="root">|<title>' || {
  echo "ERROR: SPA shell was not served at ${BASE}/" >&2
  exit 1
}

echo "✅ smoke test passed — stack is healthy and serving."
