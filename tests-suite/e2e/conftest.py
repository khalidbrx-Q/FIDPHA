"""
tests/e2e/conftest.py
---------------------
Shared fixtures for all Playwright E2E tests.

All fixtures that touch the database use transaction=True so the live
server (which runs in a separate thread) can see the data written by the
test function.
"""

import pytest
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from api.models import APIToken
from control.models import SystemConfig
from fidpha.models import Account, Contract, Contract_Product, Product, UserProfile
from fidpha.services import STATUS_ACTIVE
from sales.models import Sale, SaleImport
from sales.services import submit_sales_batch


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff",
        password="StaffPass123!",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def portal_user(db):
    account = Account.objects.create(
        code="PH-E2E",
        name="E2E Pharmacy",
        city="Casablanca",
        location="1 Test Street",
        phone="0600000000",
        email="e2e@pharmacy.ma",
        pharmacy_portal=True,
        status=STATUS_ACTIVE,
    )
    user = User.objects.create_user(
        username="portaluser",
        password="PortalPass123!",
        is_staff=False,
        email="e2e@pharmacy.ma",
    )
    UserProfile.objects.create(user=user, account=account, email_verified=True)
    return user


# ---------------------------------------------------------------------------
# Domain data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_data(db):
    """Account + active contract + one product linked — minimum for sales tests."""
    account = Account.objects.create(
        code="PH-TEST",
        name="Test Pharmacy",
        city="Casablanca",
        location="1 Test Street",
        phone="0600000000",
        email="test@pharmacy.ma",
        pharmacy_portal=True,
        status=STATUS_ACTIVE,
    )
    product = Product.objects.create(
        code="PROD-001",
        designation="Doliprane 1000",
        status=STATUS_ACTIVE,
        ppv="12.50",
    )
    now = timezone.now()
    contract = Contract.objects.create(
        title="E2E Contract",
        designation="End-to-end test contract.",
        start_date=now - timedelta(days=5),
        end_date=now + timedelta(days=30),
        account=account,
        status=STATUS_ACTIVE,
    )
    cp = Contract_Product.objects.create(
        contract=contract,
        product=product,
        external_designation="DOLI1000",
    )
    return {"account": account, "product": product, "contract": contract, "cp": cp}


@pytest.fixture
def pending_sale(base_data):
    """One pending Sale ready for staff review."""
    cp = base_data["cp"]
    product = base_data["product"]
    contract = base_data["contract"]
    dt = timezone.now() - timedelta(days=1, hours=2)
    si = SaleImport.objects.create(
        batch_id="E2E-BATCH-001",
        account_code=contract.account.code,
        external_designation=cp.external_designation,
        sale_datetime=dt,
        creation_datetime=dt,
        quantity=3,
        ppv=product.ppv,
        status=SaleImport.STATUS_ACCEPTED,
        contract_product=cp,
    )
    return Sale.objects.create(
        sale_import=si,
        contract_product=cp,
        sale_datetime=dt,
        creation_datetime=dt,
        quantity=3,
        ppv=si.ppv,
        product_ppv=product.ppv,
        status=Sale.STATUS_PENDING,
    )


# ---------------------------------------------------------------------------
# Browser helper
# ---------------------------------------------------------------------------

@pytest.fixture
def login_as(live_server, page):
    """Return a callable that logs a user in via the portal login form."""
    def _login(username, password):
        page.goto(f"{live_server.url}/portal/login/")
        page.fill("[name=username]", username)
        page.fill("[name=password]", password)
        page.click("[type=submit]")
        page.wait_for_load_state("networkidle")
    return _login
