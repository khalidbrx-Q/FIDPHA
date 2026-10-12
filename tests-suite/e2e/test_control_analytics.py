"""
tests-suite/e2e/test_control_analytics.py
-----------------------------------------
Playwright E2E tests for the staff Points analytics dashboard at
/control/analytics/. Covers initial render, live AJAX filtering,
account→contract chaining, chip rendering, and CSV export.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from playwright.sync_api import expect

from django.contrib.auth.models import Permission
from django.utils import timezone

from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import STATUS_ACTIVE
from sales.models import Sale, SaleImport


def _grant_analytics(user):
    user.user_permissions.add(Permission.objects.get(codename="view_analytics"))


def _mk_accepted_sale(cp, when, qty=2):
    si = SaleImport.objects.create(
        batch_id=f"E2E-AN-{when.isoformat()}-{qty}",
        account_code=cp.contract.account.code,
        external_designation=cp.external_designation,
        sale_datetime=when,
        creation_datetime=when,
        quantity=qty,
        ppv=cp.product.ppv,
        status=SaleImport.STATUS_ACCEPTED,
        contract_product=cp,
    )
    return Sale.objects.create(
        sale_import=si,
        contract_product=cp,
        sale_datetime=when,
        creation_datetime=when,
        quantity=qty,
        ppv=si.ppv,
        product_ppv=cp.product.ppv,
        status=Sale.STATUS_ACCEPTED,
    )


@pytest.fixture
def analytics_data(db):
    """Account + active contract + one product + two accepted sales. The
    staff superuser bypasses the view_analytics permission check."""
    account = Account.objects.create(
        code="PH-ANL", name="Analytics Pharmacy", city="Casablanca",
        location="1 Rue", phone="0600000000", email="anl@p.ma",
        pharmacy_portal=True, status=STATUS_ACTIVE,
    )
    product = Product.objects.create(
        code="P-ANL", designation="Analytics Product",
        status=STATUS_ACTIVE, ppv=Decimal("15.00"),
    )
    now = timezone.now()
    contract = Contract.objects.create(
        title="Analytics Contract", designation="d",
        start_date=now - timedelta(days=30),
        end_date=now + timedelta(days=30),
        account=account, status=STATUS_ACTIVE,
    )
    cp = Contract_Product.objects.create(
        contract=contract, product=product,
        external_designation="ANLX", points_per_unit=Decimal("1.00"),
    )
    _mk_accepted_sale(cp, now - timedelta(days=1), qty=3)
    _mk_accepted_sale(cp, now - timedelta(days=5), qty=4)
    return {"account": account, "contract": contract, "product": product}


@pytest.mark.django_db(transaction=True)
def test_dashboard_loads_with_kpi_cards(
    live_server, page, staff_user, login_as, analytics_data
):
    """Page renders and KPI cards show computed values (not 0)."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/analytics/")
    expect(page.locator("#kpiTotalPoints")).to_be_visible()
    # 3*15 + 4*15 = 105 points.
    expect(page.locator("#kpiTotalPoints")).to_have_text("105")


@pytest.mark.django_db(transaction=True)
def test_date_filter_triggers_ajax_update(
    live_server, page, staff_user, login_as, analytics_data
):
    """Setting a date-from narrows the window and fires analytics_data."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/analytics/")

    with page.expect_response(lambda r: "/control/analytics/data/" in r.url) as resp_info:
        # 10 days ago → encompasses both sales.
        past = (timezone.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        page.fill("#fldDateFrom", past)
        page.locator("#fldDateFrom").dispatch_event("change")
    assert resp_info.value.status == 200


@pytest.mark.django_db(transaction=True)
def test_permission_denied_without_view_analytics(
    live_server, page, db
):
    """Staff user without view_analytics gets 403."""
    from django.contrib.auth.models import User
    user = User.objects.create_user(
        username="limited_an", password="LimPass123!",
        is_staff=True, is_superuser=False,
    )
    user.user_permissions.add(Permission.objects.get(codename="view_sale"))
    page.goto(f"{live_server.url}/portal/login/")
    page.fill("[name=username]", "limited_an")
    page.fill("[name=password]", "LimPass123!")
    page.click("[type=submit]")
    page.wait_for_load_state("networkidle")

    resp = page.goto(f"{live_server.url}/control/analytics/")
    assert resp.status == 403


@pytest.mark.django_db(transaction=True)
def test_csv_export_download(
    live_server, page, staff_user, login_as, analytics_data
):
    """The CSV export link downloads a file whose body starts with the
    expected header row."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/analytics/")

    with page.expect_download() as dl_info:
        page.locator("#csvExportLink").click()
    download = dl_info.value
    assert download.suggested_filename.endswith(".csv")
    # Read the saved file and check the header row.
    path = download.path()
    with open(path, "rb") as f:
        head = f.read(300).decode("utf-8-sig")
    assert "Account Code" in head
    assert "Points" in head


@pytest.mark.django_db(transaction=True)
def test_account_filter_renders_chip(
    live_server, page, staff_user, login_as, analytics_data
):
    """Picking an account from the combobox fires a data refresh and the
    corresponding chip appears in the chips bar."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/analytics/")

    acc_pk = analytics_data["account"].pk
    with page.expect_response(lambda r: "/control/analytics/data/" in r.url):
        page.evaluate(
            "pk => { "
            "  const h = document.getElementById('fldAccount'); "
            "  h.value = String(pk); "
            "  h.dispatchEvent(new Event('change', {bubbles:true})); "
            "}",
            acc_pk,
        )
    # Chips bar should now mention the account.
    expect(page.locator("#chipsBar")).to_contain_text("Analytics Pharmacy")
