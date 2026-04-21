#!/bin/sh
# Boot-time tasks for api/scheduler containers.
#
# Set BOOTSTRAP_DATA=false to skip the one-time data imports (e.g. for
# the scheduler service, so only api bootstraps on fresh deployments).
# All steps are idempotent — safe to re-run on every container start.

set -e

# Import scripts under scripts/ use ``from app.*`` — /app must be on PYTHONPATH.
export PYTHONPATH="/app:${PYTHONPATH:-}"

echo "[entrypoint] running alembic upgrade head"
alembic upgrade head

if [ "${BOOTSTRAP_DATA:-true}" = "true" ]; then
    echo "[entrypoint] seeding categories / coupang fees / sample HS codes"
    python -m app.scripts.seed

    echo "[entrypoint] importing HS codes"
    python scripts/import_hs_codes.py --file /app/data/HS_CODE_20260101.xlsx

    echo "[entrypoint] importing customs duty rates (~21MB xlsx, takes a minute)"
    python scripts/import_customs_rates.py --file "/app/data/관세청_품목번호별 관세율표_20260211.xlsx"

    echo "[entrypoint] importing international shipping rates"
    python scripts/import_shipping_rates.py --lcl "/app/data/LCL해운.xls" --sea "/app/data/해운(자가).xls"

    echo "[entrypoint] seeding 20 pet-sourcing keywords"
    python -m app.scripts.seed_keywords
else
    echo "[entrypoint] BOOTSTRAP_DATA=false — skipping data imports"
fi

echo "[entrypoint] starting: $*"
exec "$@"
