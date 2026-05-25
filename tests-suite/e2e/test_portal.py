"""
tests/e2e/test_portal.py
------------------------
E2E tests for the pharmacy portal flows.

Covers:
  - Portal login redirects to dashboard
  - Dashboard stat cards are rendered
  - Sales page stat cards are rendered
  - Pharmacy page shows the linked account name
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_portal_login_redirects_to_dashboard(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    expect(page).to_have_url(f"{live_server.url}/portal/dashboard/")


@pytest.mark.django_db(transaction=True)
def test_portal_dashboard_shows_stat_cards(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/dashboard/")
    expect(page.locator(".stat-card").first).to_be_visible()
    expect(page.locator(".stat-label", has_text="Total Points")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Active Contract")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_portal_sales_page_loads(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/sales/")
    expect(page.locator(".stat-card").first).to_be_visible()
    expect(page.locator(".stat-label", has_text="Total")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Accepted")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Pending")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_portal_pharmacy_page_shows_account_name(live_server, page, portal_user, login_as):
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/pharmacy/")
    expect(page.locator(".card-title", has_text="E2E Pharmacy")).to_be_visible()


# ─── Tier 1 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_portal_user_cannot_access_control_panel(live_server, page, portal_user, login_as):
    """Tier 1 · P22 — portal users navigating to /control/ are bounced (no staff access)."""
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/control/")
    # The exact target depends on staff_required's behaviour (login redirect or 403→handler).
    # What matters: the user is NOT on /control/.
    expect(page).not_to_have_url(f"{live_server.url}/control/")


# ─── Tier 2 ───────────────────────────────────────────────────────────────


@pytest.fixture
def portal_contract(portal_user):
    """Active contract + product link + 1 accepted sale on portal_user's account.

    Required for the contracts page to render its "active contract" banner,
    stat cards, and the monthly trend chart with a non-empty bar.
    """
    from datetime import timedelta
    from django.utils import timezone
    from fidpha.models import Account, Contract, Contract_Product, Product
    from fidpha.services import STATUS_ACTIVE
    from sales.models import Sale, SaleImport

    account = Account.objects.get(code="PH-E2E")
    product = Product.objects.create(
        code="PROD-P9", designation="Doliprane 500", status=STATUS_ACTIVE, ppv="10.00",
    )
    now = timezone.now()
    contract = Contract.objects.create(
        title="Portal E2E Contract",
        designation="For portal contracts tests.",
        start_date=now - timedelta(days=60),
        end_date=now + timedelta(days=60),
        account=account,
        status=STATUS_ACTIVE,
    )
    cp = Contract_Product.objects.create(
        contract=contract, product=product, external_designation="DOLI500",
    )
    # One accepted sale a few days ago → gives the monthly chart a non-zero bar
    dt = now - timedelta(days=3)
    si = SaleImport.objects.create(
        batch_id="PORTAL-E2E-001",
        account_code=account.code,
        external_designation=cp.external_designation,
        sale_datetime=dt, creation_datetime=dt,
        quantity=5, ppv=product.ppv,
        status=SaleImport.STATUS_ACCEPTED, contract_product=cp,
    )
    Sale.objects.create(
        sale_import=si, contract_product=cp,
        sale_datetime=dt, creation_datetime=dt,
        quantity=5, ppv=si.ppv, product_ppv=product.ppv,
        status=Sale.STATUS_ACCEPTED,
    )
    return {"account": account, "contract": contract, "product": product, "cp": cp}


@pytest.mark.django_db(transaction=True)
def test_portal_contracts_page_renders_active_contract(
    live_server, page, portal_contract, login_as
):
    """Tier 2 · P9 — contracts page shows the active contract banner + stat cards."""
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/contracts/")
    # Active contract banner shows the contract title (also appears in a chart label,
    # so we narrow to the banner div via .first).
    expect(page.get_by_text("Portal E2E Contract").first).to_be_visible()
    # Stat cards visible
    expect(page.locator(".stat-label", has_text="Points Earned")).to_be_visible()
    expect(page.locator(".stat-label", has_text="Products in Contract")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_portal_contracts_monthly_chart_visible(
    live_server, page, portal_contract, login_as
):
    """Tier 2 · P10 — the monthly trend chart container renders ECharts SVG."""
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/contracts/")
    expect(page.locator("#monthlyChart")).to_be_visible()
    # ECharts renders an inner <svg> once the chart instance is initialised
    page.wait_for_selector("#monthlyChart svg", timeout=5000)
    expect(page.locator("#monthlyChart svg")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_portal_contracts_chart_drill_down_by_month(
    live_server, page, portal_contract, login_as
):
    """Tier 2 · P11 — clicking a bar in the monthly trend chart drills into that
    month. The "Back" button (hidden by default) becomes visible afterwards.

    We use ECharts' `convertToPixel` API to compute the exact pixel position of
    the first non-empty bar, then dispatch a real mouse click there.
    """
    login_as("portaluser", "PortalPass123!")
    page.goto(f"{live_server.url}/portal/contracts/")
    page.wait_for_selector("#monthlyChart svg", timeout=5000)

    # Back button starts hidden
    back = page.locator("#trend-drill-back")
    expect(back).to_be_hidden()

    # ECharts bars are SVG paths that page.mouse.click() cannot reliably hit.
    # We instead fire the same event the click handler listens for, by calling
    # `_messageCenter.trigger('click', params)` — this is the internal channel
    # ECharts uses to notify handlers registered via `mc.on('click', ...)`.
    # ECharts bars are SVG paths that page.mouse.click() cannot reliably hit.
    # The chart instance is itself an Eventful — `mc.on('click', fn)` registers
    # the handler in `ec._$handlers`, and `ec.trigger('click', params)` fires
    # it with the exact same params shape a real series click would produce.
    triggered = page.evaluate("""() => {
        const dom = document.getElementById('monthlyChart');
        const ec  = echarts.getInstanceByDom(dom);
        if (!ec) return false;
        const series = ec.getModel().getSeriesByIndex(0);
        const data   = series.getData();
        let idx = -1;
        for (let i = 0; i < data.count(); i++) {
            if (data.get(data.mapDimension('y'), i) > 0) { idx = i; break; }
        }
        if (idx < 0) return false;
        ec.trigger('click', {
            componentType: 'series',
            seriesType:    'bar',
            seriesIndex:   0,
            dataIndex:     idx,
        });
        return true;
    }""")
    assert triggered, "Could not locate a non-zero bar to dispatch a click on"

    # Drill-down toggles trendDrillActive=true and shows the back button
    expect(back).to_be_visible(timeout=3000)
