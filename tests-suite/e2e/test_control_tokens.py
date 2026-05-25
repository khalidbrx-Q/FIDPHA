"""
tests/e2e/test_control_tokens.py
-----------------------------------
E2E tests for the control panel API token flow.

Covers:
  - Tokens list page loads with create button
  - Creating a token shows the plain-text value exactly once in the reveal banner
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_tokens_list_page_loads(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/tokens/")
    expect(page.get_by_role("link", name="New Token").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_create_token_shows_plain_value(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/tokens/new/")

    page.fill("[name=name]", "E2E Test Token")
    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # Redirects to token list with a one-time reveal banner
    expect(page.locator("#revealBanner")).to_be_visible()
    # The plain token value must be non-empty
    token_value = page.locator("#fullToken").text_content()
    assert token_value and len(token_value) > 10


# ─── Tier 2 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_revoked_token_returns_401_from_api(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 2 · T6 — revoke via UI causes /api/v1/* to return 401.

    Flow: create token → confirm API call succeeds → staff clicks Revoke +
    confirms modal → identical API call now returns 401.
    """
    from django.test import Client
    from api.models import APIToken

    token_obj = APIToken(name="T6 Revoke Token")
    token_obj.save()
    raw_token = token_obj.raw_token

    # Sanity: token works before revoke
    api_client = Client()
    resp = api_client.get(
        f"/api/v1/contract/active/?account_code={base_data['account'].code}",
        HTTP_AUTHORIZATION=f"Token {raw_token}",
    )
    assert resp.status_code == 200, (
        f"Pre-revoke call should succeed: {resp.status_code} {resp.content!r}"
    )

    # Staff revokes via the detail page
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/tokens/{token_obj.pk}/")
    page.get_by_role("button", name="Revoke").click()
    page.wait_for_selector("#confirmOverlay", state="visible", timeout=5000)
    page.locator("#modalConfirmBtn").click()
    page.wait_for_load_state("networkidle")

    # DB-level confirmation the revoke landed
    token_obj.refresh_from_db()
    assert token_obj.is_active is False

    # API call now returns 401
    resp = api_client.get(
        f"/api/v1/contract/active/?account_code={base_data['account'].code}",
        HTTP_AUTHORIZATION=f"Token {raw_token}",
    )
    assert resp.status_code == 401, (
        f"Post-revoke call should be unauthorized: {resp.status_code}"
    )


@pytest.mark.django_db(transaction=True)
def test_reactivated_token_works_with_api_again(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 2 · T7 — reactivating a revoked token restores API access."""
    from django.test import Client
    from api.models import APIToken

    token_obj = APIToken(name="T7 Reactivate Token", is_active=False)
    token_obj.save()
    raw_token = token_obj.raw_token

    # Sanity: revoked token is rejected
    api_client = Client()
    resp = api_client.get(
        f"/api/v1/contract/active/?account_code={base_data['account'].code}",
        HTTP_AUTHORIZATION=f"Token {raw_token}",
    )
    assert resp.status_code == 401

    # Staff reactivates via the detail page
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/tokens/{token_obj.pk}/")
    page.get_by_role("button", name="Reactivate").click()
    page.wait_for_selector("#confirmOverlay", state="visible", timeout=5000)
    page.locator("#modalConfirmBtn").click()
    page.wait_for_load_state("networkidle")

    token_obj.refresh_from_db()
    assert token_obj.is_active is True

    # API works again
    resp = api_client.get(
        f"/api/v1/contract/active/?account_code={base_data['account'].code}",
        HTTP_AUTHORIZATION=f"Token {raw_token}",
    )
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_token_usage_stats_update_after_api_call(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 2 · T10 — usage_count reflects real API hits on the detail page.

    APITokenAuthentication bumps usage_count and writes APITokenUsageLog on
    every authenticated request. After 2 API calls, the detail page's
    "Total Calls" stat card must show 2.
    """
    from django.test import Client
    from api.models import APIToken

    token_obj = APIToken(name="T10 Stats Token")
    token_obj.save()
    raw_token = token_obj.raw_token

    # Baseline before any calls
    assert token_obj.usage_count == 0

    api_client = Client()
    for _ in range(2):
        resp = api_client.get(
            f"/api/v1/contract/active/?account_code={base_data['account'].code}",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )
        assert resp.status_code == 200

    token_obj.refresh_from_db()
    assert token_obj.usage_count == 2

    # Detail page reflects the same count in the "Total Calls" stat card
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/tokens/{token_obj.pk}/")
    stat = page.locator(".stat-card", has_text="Total Calls").locator(".stat-value")
    expect(stat).to_have_text("2")
