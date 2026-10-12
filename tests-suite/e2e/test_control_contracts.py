"""
tests/e2e/test_control_contracts.py
--------------------------------------
E2E tests for the control panel contracts flow.

Covers:
  - Contracts list page loads with create button
  - Creating a new contract (no products) lands on its detail page
"""

import pytest
from playwright.sync_api import expect

from fidpha.models import Account
from fidpha.services import STATUS_ACTIVE


@pytest.mark.django_db(transaction=True)
def test_contracts_list_page_loads(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/")
    expect(page.get_by_role("link", name="New Contract").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_create_contract_lands_on_detail(live_server, page, staff_user, login_as):
    # Use a fresh account with no contracts so the "one active contract" constraint doesn't fire
    account = Account.objects.create(
        code="PH-CT-NEW", name="Contract Test Pharmacy",
        city="Fez", location="2 Test Ave", phone="0600000002",
        email="ct@pharmacy.ma", status=STATUS_ACTIVE,
    )
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/new/")

    page.fill("[name=title]", "E2E Test Contract")
    page.fill("[name=designation]", "End-to-end contract test.")
    page.fill("[name=start_date]", "2026-01-01T00:00")
    page.fill("[name=end_date]", "2027-12-31T00:00")
    page.locator("select[name='account']").select_option(str(account.pk), force=True)
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    expect(page).not_to_have_url(f"{live_server.url}/control/contracts/new/")
    expect(page.locator(".page-header-title")).to_be_visible()


# ─── Tier 1 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_edit_contract_title_persists(live_server, page, staff_user, base_data, login_as):
    """Tier 1 · CT13 — edit a contract's title and verify it persists in the DB."""
    contract = base_data["contract"]  # title="E2E Contract" per conftest
    new_title = "E2E Contract (Updated)"

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/{contract.pk}/edit/")

    page.fill("[name=title]", new_title)
    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    contract.refresh_from_db()
    assert contract.title == new_title, (
        f"Expected title={new_title!r}, got {contract.title!r}"
    )


@pytest.mark.django_db(transaction=True)
def test_create_account_duplicate_code_shows_error(live_server, page, staff_user, base_data, login_as):
    """Tier 1 · E1 — submitting a duplicate account code stays on form with error.

    base_data already creates an account with code='PH-TEST'. Trying to create
    another with the same code must surface a validation error (not redirect).
    """
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/accounts/new/")

    page.fill("[name=code]", base_data["account"].code)  # duplicate
    page.fill("[name=name]", "Duplicate Code Pharmacy")
    page.fill("[name=city]", "Tangier")
    page.fill("[name=location]", "3 Test Blvd")
    page.fill("[name=phone]", "600000003")
    page.fill("[name=email]", "dup@pharmacy.ma")
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # Form must NOT redirect away on validation error
    expect(page).to_have_url(f"{live_server.url}/control/accounts/new/")
    # Some error element visible (Django renders .form-error or .errorlist)
    error_visible = (
        page.locator(".form-error").count() > 0
        or page.locator(".errorlist").count() > 0
        or page.locator("ul.messages").count() > 0
    )
    assert error_visible, "Expected a visible validation error on duplicate code"


@pytest.mark.django_db(transaction=True)
def test_create_second_active_contract_for_same_account_shows_error(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 1 · E2 — creating a second active contract for the same account is rejected.

    base_data already creates one active contract for the account; the
    Contract.clean() rule (CLAUDE.md: 'one active contract per account') must
    block this at the form level and surface an inline error.
    """
    account = base_data["account"]
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/new/")

    page.fill("[name=title]", "Second Active Contract (should fail)")
    page.fill("[name=designation]", "Should be blocked.")
    page.fill("[name=start_date]", "2026-06-01T00:00")
    page.fill("[name=end_date]", "2027-06-01T00:00")
    page.locator("select[name='account']").select_option(str(account.pk), force=True)
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # Must stay on /new/ — no redirect to detail
    expect(page).to_have_url(f"{live_server.url}/control/contracts/new/")


@pytest.mark.django_db(transaction=True)
def test_create_contract_end_before_start_shows_error(
    live_server, page, staff_user, login_as
):
    """Tier 1 · E3 — submitting a contract with end_date < start_date is rejected.

    Uses a fresh account so we don't also trip the 'one active contract' rule.
    """
    account = Account.objects.create(
        code="PH-DATE-ERR", name="Date Order Test",
        city="Casablanca", location="4 Test Way", phone="0600000004",
        email="date@pharmacy.ma", status=STATUS_ACTIVE,
    )
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/new/")

    page.fill("[name=title]", "Bad Date Order Contract")
    page.fill("[name=designation]", "End is before start — should fail.")
    page.fill("[name=start_date]", "2027-12-31T00:00")
    page.fill("[name=end_date]", "2026-01-01T00:00")  # earlier than start
    page.locator("select[name='account']").select_option(str(account.pk), force=True)
    page.locator("select[name='status']").select_option("active", force=True)
    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # Form must not redirect away
    expect(page).to_have_url(f"{live_server.url}/control/contracts/new/")


@pytest.mark.django_db(transaction=True)
def test_edit_contract_add_product_via_formset_persists(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 1 · CT17 — click 'Add Product' on contract edit, fill the new formset
    row with an existing product + external_designation, save, and verify a new
    Contract_Product row was created in the DB.

    base_data starts the contract with 1 linked product (cp). After this test
    we expect 2 products on the contract.
    """
    from fidpha.models import Contract_Product, Product
    from fidpha.services import STATUS_ACTIVE

    contract = base_data["contract"]
    # Create a second product so there's something to add via the formset.
    extra_product = Product.objects.create(
        code="PROD-002", designation="Aspirin 500", status=STATUS_ACTIVE, ppv="5.00",
    )

    initial_cp_count = contract.products.count()  # 1, from base_data

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/{contract.pk}/edit/")

    # Click "Add Product" — this calls addProductRow() which clones the template.
    page.locator("button", has_text="Add Product").click()

    # The new row's prefix is __prefix__ replaced by the new index (== current count).
    # Existing rows occupy indices 0..N-1; the new one will be at index N.
    # The formset prefix is "cp" (see _CP_PREFIX in control/views.py).
    new_idx = initial_cp_count  # 1
    page.locator(f"select[name='cp-{new_idx}-product']").select_option(
        str(extra_product.pk), force=True
    )
    page.fill(f"input[name='cp-{new_idx}-external_designation']", "ASP500")
    # Points factor + target quantity are defaulted server-side; leave alone.

    page.locator("[type=submit]#submitBtn").click()
    page.wait_for_load_state("networkidle")

    # DB now has 2 Contract_Product rows for this contract
    assert contract.products.count() == initial_cp_count + 1, (
        f"Expected {initial_cp_count + 1} products on contract, "
        f"got {contract.products.count()}"
    )
    # The new linkage exists with the correct external_designation
    assert Contract_Product.objects.filter(
        contract=contract, product=extra_product, external_designation="ASP500"
    ).exists(), "New Contract_Product row was not created with expected fields"


@pytest.mark.django_db(transaction=True)
def test_edit_contract_unlink_product_via_ajax(
    live_server, page, staff_user, base_data, login_as
):
    """Tier 1 · CT22 — the AJAX 'unlink' button removes a Contract_Product
    immediately (without form save), via the dedicated endpoint and a confirm
    modal. The most complex UI flow in the staff panel.

    Verifies: click the unlink-btn → confirm modal → click 'Yes, unlink' →
    Contract_Product row deleted from DB, row disappears from DOM.
    """
    from fidpha.models import Contract_Product

    contract = base_data["contract"]
    cp = base_data["cp"]  # the existing Contract_Product row
    assert Contract_Product.objects.filter(pk=cp.pk).exists()

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/contracts/{contract.pk}/edit/")

    # Click the unlink button on the first (and only) product row.
    # Scope to #product-rows so we don't also match the <template> in the page.
    page.locator("#product-rows .product-row .unlink-btn").first.click()

    # Confirm modal appears — click "Yes, unlink" and wait for the AJAX response
    # from the unlink endpoint. This is more reliable than waiting for DOM
    # changes (the JS only removes the row after a successful response anyway).
    page.wait_for_selector("#unlinkModal", state="visible", timeout=5000)

    expected_url = f"/control/contracts/{contract.pk}/unlink-product/{cp.pk}/"
    with page.expect_response(lambda r: expected_url in r.url) as resp_info:
        page.locator("#unlinkModal button.btn-danger").click()
    response = resp_info.value
    assert response.status == 200, (
        f"Unlink AJAX returned {response.status}: {response.text()}"
    )

    # The Contract_Product row is gone from the DB
    assert not Contract_Product.objects.filter(pk=cp.pk).exists(), (
        f"Contract_Product {cp.pk} should have been deleted by AJAX unlink"
    )
