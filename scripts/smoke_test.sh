#!/usr/bin/env bash
# Infra smoke test.
#
# - Brings up the full stack with docker compose
# - Waits for every service to become healthy
# - Hits nginx-proxied /health and /
# - Confirms postgres + redis respond via docker exec
# - Always tears down on exit
#
# Exit codes:
#   0  success
#   1  a check failed (container logs are dumped before exit)

set -Eeuo pipefail

# ---- Config -----------------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-itemselector_smoke}"
COMPOSE="docker compose -p ${COMPOSE_PROJECT}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"   # total seconds to wait for healthy

# Pick a free host port for nginx so the test does not collide with
# anything already bound to :80 on the developer machine.
pick_free_port() {
  python3 - <<'PY' 2>/dev/null || echo 18080
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}
export NGINX_HOST_PORT="${NGINX_HOST_PORT:-$(pick_free_port)}"

HEALTH_URL="http://localhost:${NGINX_HOST_PORT}/health"
ROOT_URL="http://localhost:${NGINX_HOST_PORT}/"

# Services that publish a Docker healthcheck
HEALTHCHECKED_SERVICES=(postgres redis api web nginx)

# ---- Helpers ----------------------------------------------------------------
log()  { printf '[smoke] %s\n' "$*" >&2; }
fail() { printf '[smoke][FAIL] %s\n' "$*" >&2; }
ok()   { printf '[smoke][OK]   %s\n' "$*" >&2; }

dump_logs() {
  log "--- docker compose ps ---"
  $COMPOSE ps || true
  for svc in "${HEALTHCHECKED_SERVICES[@]}"; do
    log "--- logs: ${svc} ---"
    $COMPOSE logs --no-color --tail=200 "$svc" || true
  done
}

cleanup() {
  local code=$?
  if [[ $code -ne 0 ]]; then
    fail "smoke test failed (exit=${code}); dumping container state"
    dump_logs
  fi
  log "bringing stack down"
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  exit $code
}
trap cleanup EXIT

# ---- Preflight --------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  fail "Docker daemon is not reachable. Start Docker Desktop and retry."
  exit 1
fi

# Ensure .env exists; fall back to .env.example so compose interpolation works
if [[ ! -f .env ]]; then
  log ".env not found; copying .env.example -> .env for this run"
  cp .env.example .env
fi

# ---- Build (separate from up so the health-wait window is not eaten by build) ----
log "building images (may take a few minutes on first run)"
$COMPOSE build

# ---- Up ---------------------------------------------------------------------
log "starting stack (NGINX_HOST_PORT=${NGINX_HOST_PORT})"
$COMPOSE up -d --no-build

# ---- Wait for healthy -------------------------------------------------------
log "waiting up to ${WAIT_TIMEOUT}s for services to become healthy"
deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
while true; do
  all_healthy=true
  for svc in "${HEALTHCHECKED_SERVICES[@]}"; do
    cid="$($COMPOSE ps -q "$svc" || true)"
    if [[ -z "$cid" ]]; then
      all_healthy=false
      break
    fi
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$cid" 2>/dev/null || echo unknown)"
    if [[ "$status" != "healthy" ]]; then
      all_healthy=false
      break
    fi
  done
  if $all_healthy; then
    ok "all services healthy"
    break
  fi
  if (( $(date +%s) >= deadline )); then
    fail "timed out waiting for services to become healthy"
    exit 1
  fi
  sleep 3
done

# ---- Infrastructure checks --------------------------------------------------
log "checking postgres (pg_isready)"
$COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER:-itemselector}" >/dev/null
ok "postgres is ready"

log "checking redis (PING)"
pong="$($COMPOSE exec -T redis redis-cli ping | tr -d '\r\n')"
if [[ "$pong" != "PONG" ]]; then
  fail "redis did not reply PONG (got: ${pong})"
  exit 1
fi
ok "redis replied PONG"

# ---- HTTP checks via nginx --------------------------------------------------
log "GET ${HEALTH_URL}"
health_code="$(curl -s -o /tmp/smoke_health.out -w '%{http_code}' "$HEALTH_URL")"
health_body="$(cat /tmp/smoke_health.out)"
if [[ "$health_code" != "200" ]]; then
  fail "GET ${HEALTH_URL} returned HTTP ${health_code}: ${health_body}"
  exit 1
fi
if ! grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' <<<"$health_body"; then
  fail "health body did not contain status=ok: ${health_body}"
  exit 1
fi
ok "api /health via nginx: 200 ${health_body}"

log "GET ${ROOT_URL}"
root_code="$(curl -s -o /dev/null -w '%{http_code}' "$ROOT_URL")"
if [[ "$root_code" != "200" ]]; then
  fail "GET ${ROOT_URL} returned HTTP ${root_code}"
  exit 1
fi
ok "web / via nginx: 200"

log "all smoke checks passed"
