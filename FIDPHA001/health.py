"""
Health check endpoint for load balancers and uptime monitors.

Hit at:  GET /health/
Returns: 200 if all checks pass, 503 otherwise.

This is called by:
- Load balancers (Railway, Render, AWS ALB) — decides if this instance
  should receive traffic.
- Uptime monitors (UptimeRobot, Better Stack) — alerts you on failure.
- Deploy pipelines — confirms a new deploy is alive before routing traffic.

Intentionally unauthenticated (load balancers can't log in) and returns
only health status, no sensitive data.
"""

import logging

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger("wininpharma.health")


@csrf_exempt
@never_cache
@require_GET
def health(request):
    """Return health status as JSON. 200 if all good, 503 if any check fails."""
    checks = {
        "db": _check_db(),
        "cache": _check_cache(),
        "migrations": _check_migrations(),
    }
    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        logger.warning("Health check failed", extra={"checks": checks})

    return JsonResponse(
        {"status": "ok" if all_ok else "degraded", **checks},
        status=200 if all_ok else 503,
    )


def _check_db():
    """Return 'ok' if DB connection works, else the error class name."""
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "ok"
    except Exception as e:
        return f"error: {type(e).__name__}"


def _check_cache():
    """Return 'ok' if cache get/set roundtrip works."""
    try:
        cache.set("_health_check", "ok", timeout=5)
        if cache.get("_health_check") == "ok":
            return "ok"
        return "error: roundtrip mismatch"
    except Exception as e:
        return f"error: {type(e).__name__}"


def _check_migrations():
    """Return 'ok' if all migrations are applied, else 'pending: N'."""
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            return "ok"
        return f"pending: {len(plan)}"
    except Exception as e:
        return f"error: {type(e).__name__}"
