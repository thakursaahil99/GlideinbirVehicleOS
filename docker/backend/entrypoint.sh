#!/bin/sh
set -e

# Wait for PostgreSQL before running anything that touches the DB.
python - <<'PY'
import os, sys, time
import psycopg
url = os.environ.get("DATABASE_URL", "postgres://crm:crm@postgres:5432/crm")
for attempt in range(60):
    try:
        psycopg.connect(url, connect_timeout=2).close()
        break
    except psycopg.OperationalError:
        time.sleep(1)
else:
    sys.exit("PostgreSQL is not reachable")
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
