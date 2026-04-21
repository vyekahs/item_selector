# Testing Runbook

This document is the single source of truth for running the itemSelector
test suites locally and in CI. It covers the three layers:

| Layer       | Tool           | Location                         | What it owns                                           |
| ----------- | -------------- | -------------------------------- | ------------------------------------------------------ |
| Unit        | pytest, vitest | `backend/tests/{api,db,scheduler,scoring,clients}`, `frontend/__tests__` | Behaviour of individual modules/components in isolation |
| Integration | pytest         | `backend/tests/integration`      | Cross-agent flows: scheduler → DB → HTTP API           |
| E2E         | Playwright     | `frontend/e2e/tests`             | User-visible flows against a real Next.js server with mocked API |

## 1. Prerequisites

- **Docker Desktop** (postgres 16 + redis 7 containers).
- **Python 3.12** (backend).
- **Node 20** and **pnpm 9** (frontend, E2E). `corepack enable` if pnpm
  is missing.
- First-time only: `pnpm exec playwright install --with-deps chromium`.

## 2. Local environment

Two postgres/redis options work out-of-the-box:

### Option A — bring up the docker-compose infra (default ports)

```bash
docker compose up -d postgres redis
export DATABASE_URL="postgresql+psycopg://itemselector:change_me_in_production@localhost:5432/postgres"
export REDIS_URL="redis://localhost:6379/0"
export USE_MOCK_CLIENTS=true
```

### Option B — reuse the existing test containers (ports 5435 / 6381)

```bash
export DATABASE_URL="postgresql+psycopg://itemselector:change_me_in_production@localhost:5435/postgres"
export REDIS_URL="redis://localhost:6381/0"
export USE_MOCK_CLIENTS=true
```

Both options create a **fresh per-session Postgres database** inside
the target server — the test fixtures create and drop
`itemselector_{api,db,scheduler,int}test_<uuid>` automatically, so no
manual schema cleanup is needed.

## 3. Backend — unit + integration

All pytest tests live under `backend/tests/`. From `backend/`:

```bash
# Install once
.venv/bin/pip install -e '.[dev]'

# Run everything
.venv/bin/pytest

# Only unit tests (skip the integration layer)
.venv/bin/pytest tests --ignore=tests/integration

# Only integration tests
.venv/bin/pytest tests/integration -v

# With coverage (HTML + XML reports)
.venv/bin/pytest --cov=app --cov-report=term --cov-report=html --cov-report=xml
open htmlcov/index.html
```

### Layer responsibilities

- **`tests/api/`** — HTTP-level tests of each FastAPI router. Uses a
  SAVEPOINT-wrapped session and `dependency_overrides[get_db]`.
- **`tests/db/`** — SQLAlchemy model + Alembic migration assertions.
- **`tests/scheduler/`** — per-job behaviour of `CollectKeywordsJob`,
  `CollectMetricsJob`, `CollectCoupangJob`, `CollectCustomsJob`,
  `CollectExchangeRateJob`, `RecalculateOpportunitiesJob`.
- **`tests/scoring/`** — pure functions in the scoring engine.
- **`tests/clients/`** — external API clients (mock + real stubs).
- **`tests/integration/`** — cross-agent flows (see `§5`).

### Postgres skip behaviour

Every DB-touching fixture tries to `CREATE DATABASE` at session start.
If Postgres is unreachable the module **skips with a clear reason**
rather than failing, so `pytest` stays green on machines without a
running compose stack. Set `DATABASE_URL` and ensure the server is up
to actually exercise these tests.

## 4. Frontend — vitest unit tests

From `frontend/`:

```bash
pnpm install
pnpm test            # vitest run (one-shot)
pnpm test:watch      # vitest watch
pnpm test:coverage   # v8 coverage in coverage/
open coverage/index.html
```

Tests live under `frontend/__tests__/`. The setup file
(`vitest.setup.ts`) stubs Recharts and `next/navigation` so
component tests don't need a real browser.

## 5. Integration tests (cross-agent)

**Scope**: scheduler jobs → DB → HTTP API.

Files (`backend/tests/integration/`):

1. **`test_opportunity_pipeline.py`** — seeds a category + seed
   keyword, runs `CollectKeywordsJob` → `CollectMetricsJob` →
   `RecalculateOpportunitiesJob`, then hits `GET /opportunities`
   and asserts:
   - top-N results are ranked by `total_score desc`
   - each row carries the 1688 deep link
   - `?category_id=` filter narrows the set as expected.
2. **`test_product_input_flow.py`** — seeds a keyword, `POST /products`
   with URL/CNY/MOQ, asserts the 2-channel `ProductScoreResponse`
   shape + recommended-channel logic, then verifies the detail +
   list endpoints.
3. **`test_coupang_rate_limit_integration.py`** — feeds 12 keywords
   into `CollectCoupangJob` with a capacity-10 bucket; asserts the
   bucket stops at 10 and `skipped_rate_limit=1`, the 10 responses
   are persisted to `api_cache`, and a second run with a fresh
   bucket short-circuits the 10 cached entries (upstream client
   called only for the two new terms).
4. **`test_feedback_roundtrip.py`** — creates a scored product,
   submits feedback, and verifies both the HTTP response and the
   `feedbacks` row + FK to `products`.

Run just these with:

```bash
cd backend
.venv/bin/pytest tests/integration -v
```

## 6. E2E tests (Playwright)

Files (`frontend/e2e/tests/`):

- `opportunities.spec.ts` — landing page renders top keywords + category filter
- `product_new.spec.ts` — form validation + redirect on success
- `product_detail.spec.ts` — radar + channel-comparison + recommended-channel
- `history.spec.ts` — paginated history with empty-state handling

The suite does **not** depend on the backend — every request is
intercepted with `page.route()` via `frontend/e2e/fixtures/api-mock.ts`,
which returns fixed JSON. The config boots Next.js on port **3100** so
it doesn't collide with a manual `pnpm dev` session.

```bash
cd frontend
pnpm install
pnpm exec playwright install --with-deps chromium
pnpm test:e2e           # headless
pnpm test:e2e:ui        # Playwright UI mode (nice for debugging)
```

Reports land in `frontend/playwright-report/`; CI uploads them as
artifacts. Traces + screenshots are captured on failure and on first
retry.

## 7. CI

### GitHub Actions — `.github/workflows/ci.yml`

Three parallel / chained jobs:

1. **backend** — Python 3.12 + Postgres service + Redis service,
   runs `pytest --cov` and uploads coverage to the `backend-coverage`
   artifact.
2. **frontend** — Node 20 + pnpm 9, runs `pnpm test:coverage` and
   `pnpm build`.
3. **e2e** — Runs after both above pass, installs Chromium,
   `pnpm test:e2e`. Uploads `playwright-report/` on failure or
   success.

### Local reproducer — `scripts/ci-test.sh`

Single entry point that mirrors the GH Actions pipeline:

```bash
bash scripts/ci-test.sh
```

Env knobs: `SKIP_DOCKER=1`, `SKIP_BACKEND=1`, `SKIP_FRONTEND=1`,
`SKIP_E2E=1` to narrow the run. See the script header for details.

## 8. Coverage targets

Numbers below are the goals agreed in the spec (§10) — they are
measured, **not** enforced at the test level. The intent is to track
trends, not to game the threshold.

| Layer          | Target |
| -------------- | ------ |
| Backend unit   | ≥ 80%  |
| Backend integration | ≥ 70% (cross-agent flows) |
| Frontend unit  | ≥ 80%  |

After running with coverage, the latest numbers are reported in:

- `backend/htmlcov/index.html` (after `pytest --cov=app --cov-report=html`)
- `frontend/coverage/index.html` (after `pnpm test:coverage`)

**Baseline snapshot at this commit** (the Tester Agent did not alter
implementation code to chase coverage — targets may or may not be hit
and will be revisited by feature authors):

- Backend: 196 existing unit tests + 7 new integration tests (across 4 files).
- Frontend: 28 existing unit tests + 4 Playwright E2E specs (`opportunities`, `product_new`, `product_detail`, `history`).

Regenerate numbers with:

```bash
cd backend && .venv/bin/pytest --cov=app --cov-report=term
cd frontend && pnpm test:coverage
```

## 9. Debugging failures

- **"PostgreSQL not reachable"** — `docker compose up -d postgres`
  (or start the `itemselector-postgres-test` container on 5435) and
  re-export `DATABASE_URL`. The fixtures skip (not fail) in this case
  so one failing test often means an unrelated pre-existing failure.
- **Scheduler test hangs** — A scheduler job is likely calling a real
  external client instead of its injected stub. Double-check the
  `coupang_client=` / `searchad_client=` kwarg is being passed.
- **`session.commit()` clobbers other tests** — Integration fixtures
  use `join_transaction_mode="create_savepoint"` so inner commits
  only release a savepoint. If you see leakage, the session wasn't
  the one yielded by the fixture — check `app.dependency_overrides[get_db]`.
- **Playwright timeout starting Next** — Port 3100 is in use; free
  it or set `E2E_BASE_URL=http://localhost:<other>` and adjust the
  `webServer.command` port accordingly.
- **Recharts-related vitest error** — Ensure `vitest.setup.ts`
  keeps its `vi.mock('recharts', …)` block; jsdom can't render its
  SVG output.
