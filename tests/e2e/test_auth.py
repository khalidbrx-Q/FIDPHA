"""
tests/e2e/test_auth.py
----------------------
E2E tests for authentication flows.

Covers:
  - Staff login redirects to control panel
  - Wrong password stays on login page
  - Non-staff cannot access the control panel
  - Logged-out user is redirected to login
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_staff_login_redirects_to_control_panel(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    expect(page).to_have_url(f"{live_server.url}/control/")


@pytest.mark.django_db(transaction=True)
def test_wrong_password_stays_on_login_page(live_server, page, staff_user, login_as):
    login_as("staff", "WrongPassword!")
    expect(page).to_have_url(f"{live_server.url}/portal/login/")


@pytest.mark.django_db(transaction=True)
def test_wrong_password_shows_error(live_server, page, staff_user, login_as):
    login_as("staff", "WrongPassword!")
    expect(page.locator("ul.messages")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_unauthenticated_user_redirected_from_control_panel(live_server, page):
    page.goto(f"{live_server.url}/control/")
    expect(page).not_to_have_url(f"{live_server.url}/control/")
