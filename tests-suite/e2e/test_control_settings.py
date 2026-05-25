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

    # Click the auto-review toggle label
    page.locator("label.toggle-switch").first.click()

    # The toggle is now ON — must click Save to persist (no auto-submit).
    # Use the .btn-primary class to disambiguate from the language-toggle
    # submit button that lives in the page header dropdown.
    page.locator("button[type=submit].btn-primary").click()
    page.wait_for_load_state("networkidle")

    # The toggle must still be ON after the page reloads
    expect(page.locator("#autoReviewToggle")).to_be_checked()

    # Verify the DB was actually updated
    config = SystemConfig.get()
    assert config.auto_review_enabled is True


# ─── Tier 3 ───────────────────────────────────────────────────────────────


def _enable_setting_toggle(page, checkbox_name):
    """Each numeric setting has a visually-hidden `*_enabled` checkbox styled
    as a toggle. Programmatically check it + fire the 'change' event so the
    page's `toggleSetting()` JS enables the matching number input."""
    page.locator(f"[name='{checkbox_name}']").evaluate("""el => {
        el.checked = true;
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""")


@pytest.mark.django_db(transaction=True)
def test_setting_max_batch_size_persists(live_server, page, staff_user, login_as):
    """Tier 3 · S3 — enabling and filling `max_batch_size` saves the new
    integer to `SystemConfig.max_batch_size`."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/settings/system/")

    _enable_setting_toggle(page, "max_batch_size_enabled")
    page.locator("[name=max_batch_size]").fill("2500")
    page.locator("button[type=submit].btn-primary").click()
    page.wait_for_load_state("networkidle")

    config = SystemConfig.get()
    assert config.max_batch_size == 2500


@pytest.mark.django_db(transaction=True)
def test_setting_api_token_rate_limit_persists(live_server, page, staff_user, login_as):
    """Tier 3 · S4 — enabling and filling `api_token_rate_limit` saves the
    new integer (per-hour limit, read by `api/throttles.py`)."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/settings/system/")

    _enable_setting_toggle(page, "api_rate_enabled")
    page.locator("[name=api_token_rate_limit]").fill("250")
    page.locator("button[type=submit].btn-primary").click()
    page.wait_for_load_state("networkidle")

    config = SystemConfig.get()
    assert config.api_token_rate_limit == 250


@pytest.mark.django_db(transaction=True)
def test_setting_ppv_tolerance_percent_persists(live_server, page, staff_user, login_as):
    """Tier 3 · S5 — enabling and filling `ppv_tolerance_percent` saves the
    new Decimal. Stored as Decimal(5, 2) so '7.5' lands as Decimal('7.50')."""
    from decimal import Decimal

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/settings/system/")

    _enable_setting_toggle(page, "ppv_tolerance_enabled")
    page.locator("[name=ppv_tolerance_percent]").fill("7.50")
    page.locator("button[type=submit].btn-primary").click()
    page.wait_for_load_state("networkidle")

    config = SystemConfig.get()
    assert config.ppv_tolerance_percent == Decimal("7.50")


@pytest.mark.django_db(transaction=True)
def test_setting_dirty_indicator_shows_after_change(
    live_server, page, staff_user, login_as
):
    """Tier 3 · S7 — the per-row `.dirty-dot` indicator appears as soon as a
    field's value differs from its baseline snapshot.

    On page load the form's JS captures every input's initial value into
    `_originals`. Any subsequent input/change event re-evaluates dirtiness
    and toggles `is-dirty` on the enclosing `.s-right` (which makes the dot
    visible via the CSS rule `.s-right.is-dirty .dirty-dot { display: block }`).
    """
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/settings/system/")

    # No row is dirty on a fresh load.
    expect(page.locator(".s-right.is-dirty")).to_have_count(0)

    # Flip the max_batch_size toggle ON (default config has 0 → unchecked).
    page.locator("[name=max_batch_size_enabled]").evaluate("""el => {
        el.checked = true;
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""")

    # The .s-right wrapping that toggle is now dirty → dot is visible.
    dirty_rows = page.locator(".s-right.is-dirty")
    expect(dirty_rows).to_have_count(1)
    expect(dirty_rows.locator(".dirty-dot")).to_be_visible()
