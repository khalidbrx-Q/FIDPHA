"""
tests/e2e/test_error_pages.py
------------------------------
E2E tests for the framework-level error pages.

Tier 3 coverage:
  - A21 unknown URL returns a 404 response
  - A22 perm-gated endpoint hit by a non-privileged staff user renders the
    custom control/403.html template with HTTP 403 status
"""

import pytest
from playwright.sync_api import expect

from django.contrib.auth.models import User


@pytest.mark.django_db(transaction=True)
def test_unknown_url_returns_404(live_server, page):
    """Tier 3 · A21 — Django's default 404 handler kicks in for unknown URLs.

    No custom `handler404` is defined, so Django returns its built-in 404 page
    (or the technical debug page when DEBUG=True). What we pin is the HTTP
    status code — 404 is the contract."""
    response = page.goto(f"{live_server.url}/this-url-does-not-exist-anywhere/")
    assert response is not None
    assert response.status == 404, (
        f"Expected 404 for unknown URL, got {response.status}"
    )


@pytest.mark.django_db(transaction=True)
def test_perm_required_view_renders_custom_403(live_server, page, login_as):
    """Tier 3 · A22 — `@perm_required` returns the custom `control/403.html`
    template with status 403 when a staff user lacks the required permission.

    Creates a fresh staff user with no Group and no individual perms, then
    hits /control/users/new/ which requires `auth.add_user`. Since the user
    isn't a superuser and lacks the perm, the decorator renders 403.html."""
    # Plain staff user — no superuser flag, no groups, no individual perms.
    User.objects.create_user(
        username="noperms", password="NoPermsPass123!", is_staff=True,
    )

    login_as("noperms", "NoPermsPass123!")
    response = page.goto(f"{live_server.url}/control/users/new/")
    assert response is not None
    assert response.status == 403, (
        f"Expected 403 for perm-denied view, got {response.status}"
    )
    # The custom 403 template is rendered (not Django's bare DEBUG page).
    expect(page.get_by_text("Access Denied").first).to_be_visible()
    expect(page.get_by_text("You don't have permission to access this page.")).to_be_visible()
