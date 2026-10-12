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

    # Accept/reject hit dedicated AJAX endpoints. `networkidle` is unreliable
    # against XHR-heavy pages — wait on the specific response instead so the
    # subsequent DB read sees the committed status.
    # sale_accept returns a 302 redirect (browser fetch sees r.redirected=true),
    # so don't constrain on status — match the URL alone.
    with page.expect_response(
        lambda r: f"/control/sales/{pending_sale.pk}/accept/" in r.url
    ):
        page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-a").click()

    pending_sale.refresh_from_db()
    assert pending_sale.status == Sale.STATUS_ACCEPTED


@pytest.mark.django_db(transaction=True)
def test_staff_can_reject_a_sale(live_server, page, staff_user, pending_sale, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)

    with page.expect_response(
        lambda r: f"/control/sales/{pending_sale.pk}/reject/" in r.url
    ):
        page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-r").click()

    pending_sale.refresh_from_db()
    assert pending_sale.status == Sale.STATUS_REJECTED


@pytest.mark.django_db(transaction=True)
def test_accepted_sale_no_longer_shows_as_pending(live_server, page, staff_user, pending_sale, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)

    # sale_accept returns a 302 redirect (browser fetch sees r.redirected=true),
    # so don't constrain on status — match the URL alone.
    with page.expect_response(
        lambda r: f"/control/sales/{pending_sale.pk}/accept/" in r.url
    ):
        page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-a").click()
    # Table re-renders after accept; the accept button must be gone for this row
    page.wait_for_selector("#salesTableWrap", state="visible", timeout=10000)
    expect(page.locator(f"tr[data-pk='{pending_sale.pk}'] .ab-a")).to_have_count(0)


# ─── Tier 1 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_sales_list_status_filter_hides_non_matching_batches(
    live_server, page, staff_user, pending_sale, login_as
):
    """Tier 1 · SR2 — status pills filter the batch list client-side.

    Setup has 1 batch with 1 PENDING sale. Clicking "accepted" should hide it
    (no accepted sales); clicking "pending" should show it again.
    """
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")

    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)
    expect(page.locator(".bl-batch")).to_have_count(1)

    # Click "Has accepted" → batch hides (no accepted sales)
    page.locator("#sfStatusPills .sf-quick", has_text="accepted").first.click()
    page.wait_for_timeout(500)
    expect(page.locator(".bl-batch:visible")).to_have_count(0)

    # Click "Has pending" → batch reappears
    page.locator("#sfStatusPills .sf-quick", has_text="pending").first.click()
    page.wait_for_timeout(500)
    expect(page.locator(".bl-batch:visible")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_sales_list_search_filters_by_batch_id(
    live_server, page, staff_user, pending_sale, login_as
):
    """Tier 1 · SR4 — typing in the batch search input filters the list.

    pending_sale fixture creates batch_id='E2E-BATCH-001'. Typing a non-match
    hides the batch; typing a matching substring shows it again. This exercises
    the same filter pipeline that the account/contract pickers use.
    """
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")

    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)
    expect(page.locator(".bl-batch")).to_have_count(1)

    # Non-match → batch hides
    page.fill("#sfBatchQ", "NOMATCH-XYZ")
    page.wait_for_timeout(500)
    expect(page.locator(".bl-batch:visible")).to_have_count(0)

    # Match → batch reappears
    page.fill("#sfBatchQ", "E2E-BATCH")
    page.wait_for_timeout(500)
    expect(page.locator(".bl-batch:visible")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_bulk_accept_multiple_sales(live_server, page, staff_user, base_data, login_as):
    """Tier 1 · SR14 — select multiple sales then bulk-accept; all flip to ACCEPTED."""
    from datetime import timedelta
    from django.utils import timezone
    from sales.models import SaleImport

    cp = base_data["cp"]
    product = base_data["product"]
    contract = base_data["contract"]

    # Create 3 pending sales in one batch
    sales = []
    for i in range(3):
        dt = timezone.now() - timedelta(days=1, hours=i + 1)
        si = SaleImport.objects.create(
            batch_id="E2E-BULK-001",
            account_code=contract.account.code,
            external_designation=cp.external_designation,
            sale_datetime=dt, creation_datetime=dt,
            quantity=1, ppv=product.ppv,
            status=SaleImport.STATUS_ACCEPTED,
            contract_product=cp,
        )
        sales.append(Sale.objects.create(
            sale_import=si, contract_product=cp,
            sale_datetime=dt, creation_datetime=dt,
            quantity=1, ppv=si.ppv, product_ppv=product.ppv,
            status=Sale.STATUS_PENDING,
        ))

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    _open_batch_and_wait_for_table(page)

    # Check all 3 row-level checkboxes (.row-chk is what bulkSelected() reads)
    for sale in sales:
        page.locator(f"tr[data-pk='{sale.pk}'] .row-chk").check()

    # Click the bulk-accept button (becomes visible when rows are selected)
    page.locator("#btnAccSel").click()

    # bulkSelected() opens a confirm modal (#confirmModal); click "Confirm".
    # The confirm triggers a POST to /control/sales/bulk-update/ — we wait on
    # that response specifically (networkidle is unreliable here and was the
    # root cause of the original flake under full-suite load).
    page.wait_for_selector("#confirmModal", state="visible", timeout=5000)
    with page.expect_response(
        lambda r: "/control/sales/bulk-update/" in r.url
    ):
        page.locator("#confirmOkBtn").click()

    # All three sales should now be ACCEPTED
    for sale in sales:
        sale.refresh_from_db()
        assert sale.status == Sale.STATUS_ACCEPTED, (
            f"Sale {sale.pk} expected ACCEPTED, got {sale.status}"
        )


@pytest.mark.django_db(transaction=True)
def test_sales_batch_submitted_via_api_appears_in_review_ui(
    live_server, page, staff_user, base_data, login_as
):
    """⭐ Tier 1 · X1 — the core business flow end-to-end:

    Pharmacy submits a batch via POST /api/v1/sales/ (the real REST endpoint,
    with a real APIToken) → staff logs into the control panel → opens the
    sales review page → the new batch is visible → opens the batch modal →
    the submitted sale row is visible with the expected designation.

    This is the single most important test in the suite. If this passes,
    the whole product works.
    """
    import json
    from datetime import timedelta
    from django.test import Client
    from django.utils import timezone
    from api.models import APIToken
    from sales.models import Sale, SaleImport

    account = base_data["account"]
    cp = base_data["cp"]  # external_designation = DOLI1000

    # ── 1) Pharmacy side: POST a real batch via /api/v1/sales/ ──────────
    # APIToken.save() generates a random raw token and stores its SHA-256 hash.
    # The raw value is exposed once via the transient .raw_token attribute.
    token_obj = APIToken(name="E2E API Token")
    token_obj.save()
    raw_token = token_obj.raw_token

    api_client = Client()
    sale_dt = (timezone.now() - timedelta(days=1, hours=2)).isoformat()
    batch_id = "E2E-API-TO-UI-001"
    payload = {
        "account_code": account.code,
        "batch_id":     batch_id,
        "sales": [{
            "external_designation": cp.external_designation,  # DOLI1000
            "sale_datetime":        sale_dt,
            "creation_datetime":    sale_dt,
            "quantity":             2,
            "ppv":                  12.50,
        }],
    }
    response = api_client.post(
        "/api/v1/sales/",
        data=json.dumps(payload),
        content_type="application/json",
        # APITokenAuthentication expects 'Token <key>' (not Bearer).
        # See api/authentication.py — case-insensitive match on "token".
        HTTP_AUTHORIZATION=f"Token {raw_token}",
    )
    assert response.status_code == 200, (
        f"API submission failed: {response.status_code} {response.content!r}"
    )

    # Confirm the records actually exist on the DB side before checking UI.
    assert SaleImport.objects.filter(batch_id=batch_id).count() == 1
    assert Sale.objects.filter(sale_import__batch_id=batch_id).count() == 1
    submitted_sale = Sale.objects.get(sale_import__batch_id=batch_id)
    assert submitted_sale.status == Sale.STATUS_PENDING  # auto-review disabled by default

    # ── 2) Staff side: open the review page, find the batch, open the modal ─
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)

    # The just-submitted batch is visible (search by batch_id to disambiguate)
    page.fill("#sfBatchQ", batch_id)
    page.wait_for_timeout(500)
    expect(page.locator(".bl-batch:visible")).to_have_count(1)

    # Open the batch modal
    page.locator(".bl-batch:visible").first.click()
    page.wait_for_selector("#salesTableWrap", state="visible", timeout=10000)

    # The sale row is visible with the product's designation
    expect(page.get_by_text("Doliprane 1000")).to_be_visible()
    # And the row references the actual Sale PK we just created via API
    expect(page.locator(f"tr[data-pk='{submitted_sale.pk}']")).to_be_visible()


# ─── Tier 3 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_sales_batch_list_date_filter_hides_out_of_range_batches(
    live_server, page, staff_user, pending_sale, login_as
):
    """Tier 3 · SR3 — setting `#sfFrom` to a future date hides all current
    batches (none have received_at >= tomorrow). Clearing the filter restores
    the list. Verifies the date_from/date_to → batches-v2 JSON pipeline.
    """
    from datetime import date, timedelta

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)
    expect(page.locator(".bl-batch")).to_have_count(1)

    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Filling #sfFrom dispatches change → fetchBatches() → /sales/api/batches-v2/
    # We wait for the API to land before asserting on visibility.
    with page.expect_response(lambda r: "/control/sales/api/batches-v2/" in r.url):
        page.locator("#sfFrom").fill(tomorrow)

    expect(page.locator(".bl-batch:visible")).to_have_count(0)
    expect(page.locator("#blEmpty")).to_be_visible()

    # Click the "Clear dates" button (only visible when a date filter is set)
    with page.expect_response(lambda r: "/control/sales/api/batches-v2/" in r.url):
        page.locator("#sfClearDate").click()

    expect(page.locator(".bl-batch:visible")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_sales_list_csv_export_returns_attachment(
    live_server, page, staff_user, pending_sale, login_as
):
    """Tier 3 · SR19 — the "Export all" option downloads a CSV attachment.

    The button lives inside an .exp-menu dropdown; we open it then click the
    second item (`doListExport(true)`). Playwright's `expect_download` catches
    the browser download; we assert the suggested filename matches the
    sales-export naming convention.
    """
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)

    # Open the export dropdown
    page.locator("button.exp-sort-btn", has_text="Export").first.click()

    with page.expect_download() as dl_info:
        page.locator(".exp-opt", has_text="Export all").click()

    download = dl_info.value
    assert download.suggested_filename.endswith(".csv"), (
        f"Expected a .csv attachment, got: {download.suggested_filename}"
    )


@pytest.mark.django_db(transaction=True)
def test_sales_list_shows_ppv_mismatch_anomaly_badge(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 3 · SR9 — when a sale's submitted `ppv` differs from the linked
    product's current PPV, the JSON API's `ppv_mismatch` count is > 0 and the
    batch row renders the `.bc-ppv` "PPV mismatch" badge.

    `base_data` creates a product with ppv=12.50; we submit a Sale with
    ppv=99.99 to force the anomaly. The mismatch detection lives entirely
    inside `sales_api_batches_v2`'s annotate clause — no submit-time check.
    """
    from datetime import timedelta
    from django.utils import timezone
    from sales.models import Sale, SaleImport

    cp = base_data["cp"]
    product = base_data["product"]
    contract = base_data["contract"]
    dt = timezone.now() - timedelta(days=1, hours=2)
    si = SaleImport.objects.create(
        batch_id="SR9-MISMATCH-001",
        account_code=contract.account.code,
        external_designation=cp.external_designation,
        sale_datetime=dt, creation_datetime=dt,
        quantity=1, ppv="99.99",  # ← deliberately differs from product.ppv (12.50)
        status=SaleImport.STATUS_ACCEPTED, contract_product=cp,
    )
    Sale.objects.create(
        sale_import=si, contract_product=cp,
        sale_datetime=dt, creation_datetime=dt,
        quantity=1, ppv=si.ppv,
        product_ppv=product.ppv,  # snapshot retains catalogue value
        status=Sale.STATUS_PENDING,
    )

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/sales/")
    page.wait_for_selector("#blSpinner", state="hidden", timeout=10000)
    page.wait_for_selector(".bl-batch", timeout=10000)

    # The batch row carries a PPV-mismatch indicator. In the row it's a span
    # with `title="N PPV mismatch"` next to a warning icon (the .bc-ppv badge
    # is reused in the batch modal chips, not the row).
    expect(page.locator(".bl-batch [title$='PPV mismatch']").first).to_be_visible()
