"""
tests/e2e/test_modal_ux.py
---------------------------
E2E tests for the cross-app modal close UX.

The sales review batch modal (`#batchModal` in `control/templates/control/
sales_list.html`) is a representative example of the modal pattern used across
the app: opens on row click, exposes a top-right X (`.bm-close-btn`), closes
on Escape (`closeBatchModal()` is wired to a document keydown handler), and
also closes on backdrop click. These two tests pin the X + Escape paths.

Tier 2 coverage:
  - Modal X button closes the batch modal
  - Escape key closes the batch modal
"""

import pytest
from playwright.sync_api import expect


def _open_batch_modal(page, live_server):
    page.goto(f"{live_server.url}/control/sales/")
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)
    page.locator(".bl-batch").first.click()
    page.wait_for_selector("#batchModal", state="visible", timeout=5000)


@pytest.mark.django_db(transaction=True)
def test_batch_modal_closes_on_x_button(
    live_server, page, staff_user, pending_sale, login_as
):
    """Tier 2 — clicking `.bm-close-btn` closes the open batch modal."""
    login_as("staff", "StaffPass123!")
    _open_batch_modal(page, live_server)

    page.locator(".bm-close-btn").click()
    expect(page.locator("#batchModal")).to_be_hidden(timeout=3000)


@pytest.mark.django_db(transaction=True)
def test_batch_modal_closes_on_escape_key(
    live_server, page, staff_user, pending_sale, login_as
):
    """Tier 2 — pressing Escape closes the open batch modal via the global
    keydown handler in sales_list.html."""
    login_as("staff", "StaffPass123!")
    _open_batch_modal(page, live_server)

    page.keyboard.press("Escape")
    expect(page.locator("#batchModal")).to_be_hidden(timeout=3000)
