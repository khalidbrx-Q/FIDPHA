"""
tests/e2e/test_control_accounts.py
------------------------------------
E2E tests for the control panel accounts flow.

Covers:
  - Accounts list page loads with search and create button
  - Creating a new account lands on its detail page
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_accounts_list_page_loads(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/accounts/")
    expect(page.locator("#accSearch")).to_be_visible()
    expect(page.get_by_role("link", name="New Account").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_create_account_lands_on_detail(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/accounts/new/")

    page.fill("[name=code]", "PH-E2E-NEW")
    page.fill("[name=name]", "New E2E Pharmacy")
    page.fill("[name=city]", "Rabat")
    page.fill("[name=location]", "1 Test Street")
    page.fill("[name=phone]", "0600000001")
    page.fill("[name=email]", "new@pharmacy.ma")
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # Redirects to the new account's detail page
    expect(page).not_to_have_url(f"{live_server.url}/control/accounts/new/")
    expect(page.locator(".page-header-title")).to_be_visible()
