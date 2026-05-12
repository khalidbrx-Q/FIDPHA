"""
tests/e2e/test_control_settings.py
-------------------------------------
E2E tests for the control panel system settings flow.

Covers:
  - System settings page loads with the auto-review toggle
  - Clicking the toggle saves immediately and reflects the new state on reload
"""

import pytest
from playwright.sync_api import expect

from control.models import SystemConfig


@pytest.mark.django_db(transaction=True)
def test_system_settings_page_loads(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/settings/system/")
    expect(page.locator(".page-header-title")).to_be_visible()
    expect(page.locator("#autoReviewToggle")).to_be_attached()


@pytest.mark.django_db(transaction=True)
def test_toggle_auto_review_saves(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/settings/system/")

    # Ensure we start with auto-review OFF (SystemConfig default)
    assert not page.locator("#autoReviewToggle").is_checked()

    # Click the visible label (the hidden input fires onchange → form submits)
    page.locator("label.toggle-switch").click()
    page.wait_for_load_state("networkidle")

    # The toggle must now be ON
    expect(page.locator("#autoReviewToggle")).to_be_checked()

    # Verify the DB was actually updated
    config = SystemConfig.get()
    assert config.auto_review_enabled is True
