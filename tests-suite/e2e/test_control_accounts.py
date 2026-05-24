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
    # 9 digits, no leading 0 — matches the Morocco local format the JS
    # phone input enforces (maxLength=9, set from PHONE_MAX_DIGITS).
    # Typing "0600000001" would be truncated client-side to "060000000",
    # silently losing the trailing digit before the form clean() runs.
    page.fill("[name=phone]", "600000001")
    page.fill("[name=email]", "new@pharmacy.ma")
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # Redirects to the new account's detail page
    expect(page).not_to_have_url(f"{live_server.url}/control/accounts/new/")
    expect(page.locator(".page-header-title")).to_be_visible()

    # Phone number must be stored with the default +212 prefix applied
    from fidpha.models import Account
    account = Account.objects.get(code="PH-E2E-NEW")
    assert account.phone == "+212600000001", (
        f"Expected '+212600000001', got '{account.phone}'"
    )


# ─── Tier 1 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_edit_account_name_persists(live_server, page, staff_user, base_data, login_as):
    """Tier 1 · AC21 — edit an account's name via the form; DB + list reflect new value."""
    account = base_data["account"]  # code=PH-TEST, name="Test Pharmacy"
    new_name = "Test Pharmacy (Renamed)"

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/accounts/{account.pk}/edit/")

    # Replace the name field and submit
    page.fill("[name=name]", new_name)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # DB now holds the new name
    account.refresh_from_db()
    assert account.name == new_name, f"Expected {new_name!r}, got {account.name!r}"

    # And it appears on the accounts list page
    page.goto(f"{live_server.url}/control/accounts/")
    expect(page.get_by_text(new_name).first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_edit_account_toggle_auto_review_persists(live_server, page, staff_user, base_data, login_as):
    """Tier 1 · AC23 — toggle per-account auto_review_enabled and verify it persists.

    Note: the per-account checkbox is DISABLED in the UI when the global
    SystemConfig.auto_review_enabled is OFF (this is intentional — auto-review
    requires BOTH flags to be on). The conftest reset turns the global flag off,
    so we must enable it here before the per-account checkbox becomes editable.
    """
    from control.models import SystemConfig

    # Enable global auto-review so the per-account checkbox is editable.
    config = SystemConfig.get()
    config.auto_review_enabled = True
    config.save()

    account = base_data["account"]
    account.refresh_from_db()
    initial_state = account.auto_review_enabled

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/accounts/{account.pk}/edit/")

    # The real checkbox is visually hidden inside a custom toggle-switch UI
    # (see accounts_form.html). Click the wrapping label — the actual click
    # target a user would use — instead of the hidden <input> directly.
    toggle = page.locator(".toggle-switch:has([name=auto_review_enabled])")
    toggle.click()

    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    account.refresh_from_db()
    assert account.auto_review_enabled is (not initial_state), (
        f"auto_review_enabled did not flip — still {account.auto_review_enabled}"
    )
