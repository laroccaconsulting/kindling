# Slim Superset for Kindling: DuckDB driver, SQLite metadata, no Celery/Redis (ADR 0003).
FROM apache/superset:5.0.0

USER root
# Keep duckdb in step with the version that writes the warehouse (uv.lock).
RUN uv pip install --no-cache --python /app/.venv/bin/python \
      "duckdb==1.5.5" "duckdb-engine==0.17.0"

COPY superset_config.py /app/pythonpath/superset_config.py
COPY entrypoint.sh /app/kindling/entrypoint.sh
COPY assets /app/kindling/assets
RUN chmod +x /app/kindling/entrypoint.sh

USER superset
ENTRYPOINT ["/app/kindling/entrypoint.sh"]
