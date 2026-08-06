#!/bin/sh
# ---------------------------------------------------------------------------
# Container entrypoint: wait for the database, migrate, optionally seed, then
# exec the given command (gunicorn by default).
# ---------------------------------------------------------------------------
set -e

if [ "${DB_ENGINE}" = "mysql" ]; then
  echo "Waiting for MySQL at ${DB_HOST:-127.0.0.1}:${DB_PORT:-3306} ..."
  attempts=0
  until python -c "
import os, sys, pymysql
try:
    pymysql.connect(
        host=os.environ.get('DB_HOST', '127.0.0.1'),
        port=int(os.environ.get('DB_PORT', 3306)),
        user=os.environ.get('DB_USER', ''),
        password=os.environ.get('DB_PASSWORD', ''),
    ).close()
except Exception as exc:
    sys.exit(1)
" 2>/dev/null; do
    attempts=$((attempts + 1))
    if [ "${attempts}" -ge 60 ]; then
      echo "Database did not become available in time." >&2
      exit 1
    fi
    sleep 2
  done
  echo "MySQL is ready."
fi

echo "Applying database migrations ..."
python manage.py migrate --noinput

if [ "${SEED_DEMO_DATA}" = "1" ]; then
  echo "Seeding demo data ..."
  python manage.py seed_demo_data
fi

echo "Starting: $*"
exec "$@"
