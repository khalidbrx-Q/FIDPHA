"""
tests/e2e/test_sales_review.py
-------------------------------
E2E tests for the control panel sales review flow.

The sales list page is a JS SPA: batches load via AJAX into #blRows, and the
sales table only appears after clicking a batch row (opens a modal).
Accept/reject are triggered via JavaScript buttons, not HTML form submissions.

Covers:
  - Sales list page loads and shows pending sales (inside the batch modal)
  - Staff can accept a pending sale
  - Staff can reject a pending sale
  - Accepted sale no longer shows its accept button
"""

import pytest
from playwright.sync_api import expect

from sales.models import Sale


def _open_batch_and_wait_for_table(page):
    """Wait for batch list to load, click the first batch, wait for the sales table."""
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)
    page.locator(".bl-batch").first.click()
    page.wait_for_selector("#salesTableWrap", state="visible", timeout=10000)


@pytest.mark.django_db(transaction=True)
def test_sales_list_shows_pending_sale(live_server, page, staff_user, pending_sale, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)
    expect(page.get_by_text("Doliprane 1000")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_staff_can_accept_a_sale(live_server, page, staff_user, pending_sale, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)

    page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-a").click()
    page.wait_for_load_state("networkidle")

    pending_sale.refresh_from_db()
    assert pending_sale.status == Sale.STATUS_ACCEPTED


@pytest.mark.django_db(transaction=True)
def test_staff_can_reject_a_sale(live_server, page, staff_user, pending_sale, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)

    page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-r").click()
    page.wait_for_load_state("networkidle")

    pending_sale.refresh_from_db()
    assert pending_sale.status == Sale.STATUS_REJECTED


@pytest.mark.django_db(transaction=True)
def test_accepted_sale_no_longer_shows_as_pending(live_server, page, staff_user, pending_sale, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)

    page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-a").click()
    page.wait_for_load_state("networkidle")
    # Table re-renders after accept; the accept button must be gone for this row
    page.wait_for_selector("#salesTableWrap", state="visible", timeout=10000)
    expect(page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-a")).to_have_count(0)
