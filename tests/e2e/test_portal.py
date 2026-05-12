"""
tests/e2e/test_portal.py
------------------------
E2E tests for the pharmacy portal flows.

Covers:
  - Portal login redirects to dashboard
  - Dashboard stat cards are rendered
  - Sales page stat cards are rendered
  - Pharmacy page shows the linked account name
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_portal_login_redirects_to_dashboard(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    expect(page).to_have_url(f"{live_server.url}/portal/dashboard/")


@pytest.mark.django_db(transaction=True)
def test_portal_dashboard_shows_stat_cards(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/dashboard/")
    expect(page.locator(".stat-card").first).to_be_visible()
    expect(page.locator(".stat-label", has_text="Total Points")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Active Contract")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_portal_sales_page_loads(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/sales/")
    expect(page.locator(".stat-card").first).to_be_visible()
    expect(page.locator(".stat-label", has_text="Total")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Accepted")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Pending")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_portal_pharmacy_page_shows_account_name(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/pharmacy/")
    expect(page.locator(".card-title", has_text="E2E Pharmacy")).to_be_visible()
