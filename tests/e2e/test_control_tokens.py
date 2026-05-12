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
