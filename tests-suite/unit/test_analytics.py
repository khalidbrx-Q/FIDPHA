"""
tests-suite/unit/test_analytics.py
----------------------------------
Server-side tests for the /control/analytics/ Points dashboard: permission
gating, response shapes of each endpoint, filter plumbing, and the numeric
correctness of _compute_analytics (totals + awarded baseline).
"""

import csv
import io
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.utils import timezone

from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import STATUS_ACTIVE
from sales.models import Sale, SaleImport


def _mk_sale(cp, when, qty=2, ppv="10.00", status=Sale.STATUS_ACCEPTED):
    """Create a SaleImport + Sale pair at `when`; defaults to ACCEPTED."""
    si = SaleImport.objects.create(
        batch_id=f"B-{when.isoformat()}-{qty}",
        account_code=cp.contract.account.code,
        external_designation=cp.external_designation,
        sale_datetime=when,
        creation_datetime=when,
        quantity=qty,
        ppv=Decimal(ppv),
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
        status=status,
    )


class AnalyticsBaseFixture(TestCase):
    """Shared setup for analytics tests: one account, one product, one
    active contract linking them, and three accepted Sales — two in the
    current month, one 90 days ago (for baseline tests)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(
            code="PH-AN", name="Analytics Pharmacy", city="C", location="L",
            phone="0600000000", email="an@p.ma",
            pharmacy_portal=True, status=STATUS_ACTIVE,
        )
        cls.product = Product.objects.create(
            code="P-AN", designation="Analytics Product",
            status=STATUS_ACTIVE, ppv=Decimal("10.00"),
        )
        now = timezone.now()
        cls.contract = Contract.objects.create(
            title="Analytics Contract",
            designation="Analytics test contract.",
            start_date=now - timedelta(days=120),
            end_date=now + timedelta(days=30),
            account=cls.account,
            status=STATUS_ACTIVE,
        )
        cls.cp = Contract_Product.objects.create(
            contract=cls.contract, product=cls.product,
            external_designation="PANX", points_per_unit=Decimal("1.00"),
        )
        # Three accepted sales: two recent (within last 10 days),
        # one 90 days ago (baseline material).
        _mk_sale(cls.cp, now - timedelta(days=1), qty=2)   # 2*10*1 = 20
        _mk_sale(cls.cp, now - timedelta(days=3), qty=5)   # 5*10*1 = 50
        _mk_sale(cls.cp, now - timedelta(days=90), qty=4)  # 4*10*1 = 40 (baseline)

    def _mk_staff(self, with_analytics=True):
        user = User.objects.create_user(
            username=f"staff_{with_analytics}_{self.id()}",
            password="pw", is_staff=True,
        )
        if with_analytics:
            user.user_permissions.add(
                Permission.objects.get(codename="view_analytics")
            )
        return user


class AnalyticsPermissionTests(AnalyticsBaseFixture):
    """The dashboard + its sibling endpoints all require view_analytics."""

    def test_dashboard_denied_without_perm(self):
        user = self._mk_staff(with_analytics=False)
        c = Client()
        c.force_login(user)
        # @perm_required renders control/403.html with status 403.
        self.assertEqual(c.get("/control/analytics/").status_code, 403)

    def test_dashboard_allowed_with_perm(self):
        user = self._mk_staff(with_analytics=True)
        c = Client()
        c.force_login(user)
        self.assertEqual(c.get("/control/analytics/").status_code, 200)

    def test_data_endpoint_denied_without_perm(self):
        user = self._mk_staff(with_analytics=False)
        c = Client()
        c.force_login(user)
        self.assertEqual(c.get("/control/analytics/data/").status_code, 403)

    def test_csv_export_denied_without_perm(self):
        user = self._mk_staff(with_analytics=False)
        c = Client()
        c.force_login(user)
        self.assertEqual(c.get("/control/analytics/export/").status_code, 403)


class AnalyticsDataEndpointTests(AnalyticsBaseFixture):
    """JSON shape + filter plumbing for /control/analytics/data/."""

    def setUp(self):
        self.user = self._mk_staff(with_analytics=True)
        self.client = Client()
        self.client.force_login(self.user)

    def test_json_contains_required_keys(self):
        resp = self.client.get("/control/analytics/data/")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        # Sample of mandatory keys consumed by the template.
        for key in ("kpi_total_points", "kpi_daily_avg", "kpi_total_products",
                    "kpi_total_accounts", "kpi_pending_points",
                    "chart_timeline_lbls", "chart_timeline_keys",
                    "chart_timeline_pts", "chart_submissions",
                    "awarded_lbls", "awarded_vals",
                    "heatmap_data", "heatmap_range",
                    "chart_top_products", "chart_acct_labels",
                    "chart_acct_data", "breakdown", "breakdown_total"):
            self.assertIn(key, payload, f"missing key: {key}")

    def test_total_points_matches_accepted_sum(self):
        resp = self.client.get("/control/analytics/data/")
        payload = json.loads(resp.content)
        # 20 + 50 + 40 = 110 across all three sales.
        self.assertEqual(payload["kpi_total_points"], 110)

    def test_account_filter_narrows_to_scope(self):
        # Second account + contract + sale that we expect to be filtered out.
        other = Account.objects.create(
            code="PH-OTHER", name="Other", city="C", location="L",
            phone="0611111111", email="o@p.ma",
            pharmacy_portal=True, status=STATUS_ACTIVE,
        )
        now = timezone.now()
        ocontract = Contract.objects.create(
            title="Other", designation="d",
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=10),
            account=other, status=STATUS_ACTIVE,
        )
        ocp = Contract_Product.objects.create(
            contract=ocontract, product=self.product,
            external_designation="OTHX",
        )
        _mk_sale(ocp, now - timedelta(days=1), qty=10)  # 10*10*1 = 100

        # Unfiltered sees everything.
        unfiltered = json.loads(self.client.get("/control/analytics/data/").content)
        self.assertEqual(unfiltered["kpi_total_points"], 210)

        # Filtered by original account excludes the other row.
        scoped = json.loads(
            self.client.get(f"/control/analytics/data/?account={self.account.pk}").content
        )
        self.assertEqual(scoped["kpi_total_points"], 110)

    def test_awarded_baseline_seeds_cumulative_line(self):
        """Pre-filter cumulative baseline seeds the first value of
        awarded_vals when the filter window excludes earlier sales."""
        now = timezone.now()
        # Date range: last 10 days only — the 90-day-old sale (40 pts) is
        # outside the window and must become the awarded_baseline.
        date_from = (now - timedelta(days=10)).strftime("%Y-%m-%d")
        date_to   = now.strftime("%Y-%m-%d")
        resp = self.client.get(
            f"/control/analytics/data/?date_from={date_from}&date_to={date_to}"
        )
        payload = json.loads(resp.content)
        # The last value of awarded_vals = baseline (40) + in-scope points (70) = 110.
        self.assertEqual(payload["awarded_vals"][-1], 110)
        # And the first value must be at least the baseline (40) — i.e. the
        # cumulative does NOT restart from zero when a baseline exists.
        self.assertGreaterEqual(payload["awarded_vals"][0], 40)


class AnalyticsCsvExportTests(AnalyticsBaseFixture):
    """CSV export: content type, header row, and row count."""

    def setUp(self):
        self.user = self._mk_staff(with_analytics=True)
        self.client = Client()
        self.client.force_login(self.user)

    def test_csv_streams_with_expected_headers(self):
        resp = self.client.get("/control/analytics/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = b"".join(resp.streaming_content).decode("utf-8-sig")
        reader = csv.reader(io.StringIO(body))
        rows = list(reader)
        header = rows[0]
        # Spot-check a few headers that must stay stable (external consumers).
        for col in ("Account Code", "Product Code", "Qty", "Points"):
            self.assertIn(col, header)
        # 3 accepted sales → 3 data rows.
        self.assertEqual(len(rows) - 1, 3)
