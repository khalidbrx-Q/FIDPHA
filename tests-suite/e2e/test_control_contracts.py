"""
tests/e2e/test_control_contracts.py
--------------------------------------
E2E tests for the control panel contracts flow.

Covers:
  - Contracts list page loads with create button
  - Creating a new contract (no products) lands on its detail page
"""

import pytest
from playwright.sync_api import expect

from fidpha.models import Account
from fidpha.services import STATUS_ACTIVE


@pytest.mark.django_db(transaction=True)
def test_contracts_list_page_loads(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/")
    expect(page.get_by_role("link", name="New Contract").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_create_contract_lands_on_detail(live_server, page, staff_user, login_as):
    # Use a fresh account with no contracts so the "one active contract" constraint doesn't fire
    account = Account.objects.create(
        code="PH-CT-NEW", name="Contract Test Pharmacy",
        city="Fez", location="2 Test Ave", phone="0600000002",
        email="ct@pharmacy.ma", status=STATUS_ACTIVE,
    )
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/new/")

    page.fill("[name=title]", "E2E Test Contract")
    page.fill("[name=designation]", "End-to-end contract test.")
    page.fill("[name=start_date]", "2026-01-01T00:00")
    page.fill("[name=end_date]", "2027-12-31T00:00")
    page.locator("select[name='account']").select_option(str(account.pk), force=True)
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    expect(page).not_to_have_url(f"{live_server.url}/control/contracts/new/")
    expect(page.locator(".page-header-title")).to_be_visible()
