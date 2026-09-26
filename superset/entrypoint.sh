#!/usr/bin/env bash
# Initialize Superset on first boot, import Kindling's dashboards, then serve.
set -euo pipefail

superset db upgrade
superset fab create-admin \
  --username admin --firstname Kindling --lastname Admin \
  --email admin@example.com --password "${SUPERSET_ADMIN_PASSWORD:-admin}" || true
superset init

if [ -f "${KINDLING_DUCKDB_PATH:-/data/kindling.duckdb}" ]; then
  bundle=/tmp/kindling-dashboards.zip
  (cd /app/kindling/assets && python -m zipfile -c "$bundle" kindling)
  superset import-dashboards --path "$bundle" --username admin
else
  echo "No warehouse at ${KINDLING_DUCKDB_PATH:-/data/kindling.duckdb}; run \`kindling run\` first. Skipping dashboard import."
fi

exec /app/docker/entrypoints/run-server.sh
