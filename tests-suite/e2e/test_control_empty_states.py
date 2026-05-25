"""
tests/e2e/test_control_empty_states.py
---------------------------------------
E2E tests for the "no data" placeholders.

Lists in the control panel render different markup when the underlying queryset
is empty — accounts/products/contracts show a server-rendered empty card with
a CTA; sales review shows a JS-driven `#blEmpty` message inside the batch list.
Both must render correctly for first-run users.

Tier 2 coverage:
  - AC8  accounts list with 0 rows shows "No accounts yet"
  - SR23 sales list with 0 batches shows the no-batches placeholder
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_accounts_list_shows_empty_state_when_no_accounts(
    live_server, page, staff_user, login_as
):
    """Tier 2 · AC8 — with zero Account rows, the accounts list page shows the
    "No accounts yet" empty card instead of the table. `staff_user` does not
    create any accounts, so the DB is empty for this fixture set."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/accounts/")
    expect(page.get_by_text("No accounts yet")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_sales_list_shows_empty_state_when_no_batches(
    live_server, page, staff_user, login_as
):
    """Tier 2 · SR23 — with zero SaleImport rows, /control/sales/ shows the
    `#blEmpty` placeholder ("No batches match the current filters.") once
    the spinner hides. Tests the JS-driven empty path of the sales SPA."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")

    # Wait for the loader to finish — JS then toggles #blEmpty visible.
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    expect(page.locator("#blEmpty")).to_be_visible()
