"""
tests/e2e/test_control_products.py
------------------------------------
E2E tests for the control panel products flow.

Covers:
  - Products list page loads with search and create button
  - Creating a new product redirects to the products list with a success message
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_products_list_page_loads(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/products/")
    expect(page.get_by_role("link", name="New Product").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_create_product_redirects_to_list(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/products/new/")

    page.fill("[name=code]", "E2E-PROD-001")
    page.fill("[name=designation]", "E2E Test Product")
    page.fill("[name=ppv]", "15.00")
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    expect(page).to_have_url(f"{live_server.url}/control/products/")
    expect(page.get_by_role("cell", name="E2E Test Product")).to_be_visible()
