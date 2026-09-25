"""Superset settings for the Kindling reference stack (single container, read-only DuckDB)."""

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db?check_same_thread=false"

# No Celery or Redis: simple in-process caching is plenty for a demo-sized warehouse.
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 3600}
DATA_CACHE_CONFIG = CACHE_CONFIG
FILTER_STATE_CACHE_CONFIG = CACHE_CONFIG
EXPLORE_FORM_DATA_CACHE_CONFIG = CACHE_CONFIG

FEATURE_FLAGS = {
    "DASHBOARD_RBAC": False,
    "ENABLE_TEMPLATE_PROCESSING": False,
}

# The warehouse is synthetic and mounted read-only; allow file-based DuckDB URIs.
PREVENT_UNSAFE_DB_CONNECTIONS = False
ROW_LIMIT = 50000
SQLLAB_TIMEOUT = 120
SUPERSET_WEBSERVER_TIMEOUT = 120

# Public, read-only demo mode (hosted reference implementation): anonymous users get
# the Gamma-like "Public" role. Off locally unless KINDLING_SUPERSET_PUBLIC=1.
if os.environ.get("KINDLING_SUPERSET_PUBLIC") == "1":
    AUTH_ROLE_PUBLIC = "Public"
    PUBLIC_ROLE_LIKE = "Gamma"

TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True
