"""
tests-suite/conftest.py
-----------------------
Shared pytest fixtures + environment setup for all test suites
(unit + e2e). Lives outside the Django repo so test code is never
shipped to production.
"""

import os

# Allow synchronous Django ORM calls from within pytest-playwright's async
# event loop. Without this, django_db_setup raises SynchronousOnlyOperation
# because Playwright's session-scoped event loop is already running when
# pytest-django tries to create the test database.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


# ---------------------------------------------------------------------------
# Test isolation: reset SystemConfig + cache before each test
# ---------------------------------------------------------------------------
# Phase 1.6 (Redis cache) and the SystemConfig refactor made several runtime
# limits dynamic (max_batch_size, api_token_rate_limit, etc.). Several legacy
# tests still assume the OLD hardcoded behavior (e.g. MAX_BATCH_SIZE = 50000).
#
# To keep tests deterministic AND match those old assumptions:
#   1. Reset SystemConfig to test-friendly defaults before each test.
#   2. Clear the Django cache so stale cached values don't leak between tests.
# ---------------------------------------------------------------------------

import pytest


@pytest.fixture(autouse=True)
def _reset_systemconfig_and_cache(db):
    """Runs before every test that uses the DB. Restores test-baseline state."""
    from django.core.cache import cache
    from control.models import SystemConfig

    # Hard-set the values tests historically relied on. The legacy test suite
    # was written across multiple eras with different limit assumptions:
    #   - test_raises_batch_too_large_error sends 50001 rows expecting error
    #   - test_returns_400_when_batch_too_large sends 5001 rows expecting error
    # max_batch_size = 5000 satisfies BOTH (5001 > 5000 and 50001 > 5000).
    config = SystemConfig.get()
    config.max_batch_size = 5000           # smaller than oldest test assumption
    config.api_token_rate_limit = 0        # 0 = unlimited (default)
    config.auto_review_enabled = False     # opt-in feature; tests assume off
    config.save()

    # Wipe Django cache so the change above is visible to code paths that
    # cache SystemConfig values (e.g. submit_sales_batch, APITokenThrottle).
    cache.clear()

    yield
    # Nothing to teardown — Django's TestCase wraps each test in a transaction
    # that rolls back automatically.
