#!/usr/bin/env bash
# Local CI driver.
#
# Mirrors `.github/workflows/ci.yml` so you can reproduce CI locally
# on a machine without GitHub Actions. Steps (all rollback on failure):
#
#   1. docker compose up -d postgres redis   (default ports 5432 / 6379)
#   2. pytest  (backend, with coverage)
#   3. vitest  (frontend, with coverage)
#   4. pnpm build (frontend, production build sanity)
#   5. playwright test (frontend, E2E)
#
# Env knobs:
#   SKIP_DOCKER=1      → do not start docker compose (assume already up)
#   SKIP_BACKEND=1     → skip pytest
#   SKIP_FRONTEND=1    → skip vitest + build
#   SKIP_E2E=1         → skip playwright
#   DATABASE_URL       → override pytest target
#   REDIS_URL          → override pytest target
#
# Exit codes:
#   0  all green
#   1  one or more layers failed

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log()  { printf '[ci-test] %s\n' "$*" >&2; }
fail() { printf '[ci-test][FAIL] %s\n' "$*" >&2; }
ok()   { printf '[ci-test][OK]   %s\n' "$*" >&2; }

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://itemselector:change_me_in_production@localhost:5432/postgres}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export USE_MOCK_CLIENTS="${USE_MOCK_CLIENTS:-true}"

BACKEND_EXIT=0
FRONTEND_EXIT=0
E2E_EXIT=0

bring_infra_up() {
  if [[ "${SKIP_DOCKER:-0}" == "1" ]]; then
    log "SKIP_DOCKER=1, skipping docker compose up"
    return
  fi
  log "starting postgres + redis via docker compose"
  docker compose up -d postgres redis >/dev/null
  log "waiting for postgres/redis healthy"
  local deadline
  deadline=$(( $(date +%s) + 120 ))
  while true; do
    local pg redis
    pg=$(docker compose ps -q postgres || true)
    redis=$(docker compose ps -q redis || true)
    local pg_ok=0 redis_ok=0
    if [[ -n "$pg" ]] && docker inspect -f '{{.State.Health.Status}}' "$pg" 2>/dev/null | grep -q healthy; then
      pg_ok=1
    fi
    if [[ -n "$redis" ]] && docker inspect -f '{{.State.Health.Status}}' "$redis" 2>/dev/null | grep -q healthy; then
      redis_ok=1
    fi
    if [[ "$pg_ok" == "1" && "$redis_ok" == "1" ]]; then
      ok "postgres + redis healthy"
      return
    fi
    if (( $(date +%s) >= deadline )); then
      fail "timed out waiting for docker compose infra"
      exit 1
    fi
    sleep 2
  done
}

run_backend() {
  if [[ "${SKIP_BACKEND:-0}" == "1" ]]; then
    log "SKIP_BACKEND=1, skipping pytest"
    return 0
  fi
  log "backend: installing + pytest"
  (
    cd backend
    # Prefer the existing .venv; fall back to the global pytest.
    if [[ -x .venv/bin/pytest ]]; then
      .venv/bin/pytest --cov=app --cov-report=term --cov-report=html --cov-report=xml tests/
    else
      python3 -m pip install -e '.[dev]' >/dev/null
      python3 -m pytest --cov=app --cov-report=term --cov-report=html --cov-report=xml tests/
    fi
  )
}

run_frontend() {
  if [[ "${SKIP_FRONTEND:-0}" == "1" ]]; then
    log "SKIP_FRONTEND=1, skipping vitest + build"
    return 0
  fi
  log "frontend: installing, vitest, build"
  (
    cd frontend
    if ! command -v pnpm >/dev/null 2>&1; then
      corepack enable
      corepack prepare pnpm@9.12.0 --activate
    fi
    pnpm install --frozen-lockfile
    pnpm test:coverage
    pnpm build
  )
}

run_e2e() {
  if [[ "${SKIP_E2E:-0}" == "1" ]]; then
    log "SKIP_E2E=1, skipping Playwright"
    return 0
  fi
  log "frontend: Playwright E2E"
  (
    cd frontend
    pnpm exec playwright install --with-deps chromium
    pnpm test:e2e
  )
}

bring_infra_up

run_backend  || BACKEND_EXIT=$?
run_frontend || FRONTEND_EXIT=$?
run_e2e      || E2E_EXIT=$?

echo
echo "============================================================"
echo "  CI summary"
echo "============================================================"
printf '  backend  : %s\n' "$([[ $BACKEND_EXIT  -eq 0 ]] && echo PASS || echo FAIL)"
printf '  frontend : %s\n' "$([[ $FRONTEND_EXIT -eq 0 ]] && echo PASS || echo FAIL)"
printf '  e2e      : %s\n' "$([[ $E2E_EXIT      -eq 0 ]] && echo PASS || echo FAIL)"
echo "============================================================"

overall=$(( BACKEND_EXIT + FRONTEND_EXIT + E2E_EXIT ))
if (( overall != 0 )); then
  fail "one or more layers failed"
  exit 1
fi
ok "all layers passed"
