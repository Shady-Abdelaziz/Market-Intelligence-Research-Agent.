#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-api}"

# Wait briefly for Postgres if configured
if [[ "${DATABASE_URL:-}" == postgresql* ]]; then
  python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
for i in range(30):
    try:
        create_engine(url).connect().execute(text("SELECT 1"))
        break
    except Exception as e:
        print(f"waiting for postgres ({i}): {e}", file=sys.stderr)
        time.sleep(1)
else:
    print("postgres not reachable, continuing anyway", file=sys.stderr)
PY
fi

# Run migrations on api boot (idempotent)
if [[ "$MODE" == "api" ]]; then
  alembic upgrade head || echo "alembic upgrade failed (might be sqlite first-boot); continuing"
fi

case "$MODE" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}"
    ;;
  worker)
    exec arq app.workers.arq_settings.WorkerSettings
    ;;
  *)
    echo "unknown mode: $MODE" >&2
    exit 1
    ;;
esac
