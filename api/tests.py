"""
api/tests.py
------------
Test suite for the public REST API (api app).

Covers all three endpoints:
  - GET  /api/v1/contract/active/   — ActiveContractView
  - POST /api/v1/sales/             — SalesSubmitView
  - POST /api/v1/contract/sync/     — ContractSyncView

How to run:
    python manage.py test api
    python manage.py test api.tests.ActiveContractViewTests
    python manage.py test api.tests.SalesSubmitViewTests
    python manage.py test api.tests.ContractSyncViewTests

Author: FIDPHA Dev Team
Last updated: April 2026
"""

import re
import threading
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import APIToken
from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import STATUS_ACTIVE, STATUS_INACTIVE
from sales.models import Sale, SaleImport

_USING_SQLITE = settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------

def make_account(code="PH-TEST", name="Test Pharmacy", status=STATUS_ACTIVE):
    return Account.objects.create(
        code=code, name=name,
        city="Casablanca", location="123 Test Street",
        phone="0600000000", email="test@pharmacy.ma",
        pharmacy_portal=True, status=status,
    )


def make_product(code="PROD-001", designation="Doliprane 1000", status=STATUS_ACTIVE):
    return Product.objects.create(code=code, designation=designation, status=status)


def make_contract(account, status=STATUS_ACTIVE, days_back=1, days_ahead=30):
    now = timezone.now()
    return Contract.objects.create(
        title="Test Contract",
        designation="Test contract description.",
        start_date=now - timedelta(days=days_back),
        end_date=now + timedelta(days=days_ahead),
        account=account,
        status=status,
    )


def make_api_token(name="Test Token", is_active=True):
    return APIToken.objects.create(name=name, is_active=is_active)


def make_sale_row(external_designation="DOLI1000", hours_ago=2, quantity=5, ppv=12.50):
    """Return a valid sale row dict for use in POST /api/v1/sales/ requests."""
    dt = (timezone.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "external_designation": external_designation,
        "sale_datetime":        dt,
        "creation_datetime":    dt,
        "quantity":             quantity,
        "ppv":                  ppv,
    }


# ===========================================================================
# Endpoint 1 — GET /api/v1/contract/active/
# ===========================================================================

class ActiveContractViewTests(TestCase):

    API_URL = "/api/v1/contract/active/"

    def setUp(self):
        cache.clear()
        self.token = make_api_token(name="Integration Token")

        self.anon_client = APIClient()
        self.auth_client = APIClient()
        self.auth_client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.token}")

        self.account          = make_account(code="PH-001", name="Pharmacie Saada")
        self.product          = make_product(code="PROD-001", designation="Doliprane 1000")
        self.contract         = make_contract(self.account, status=STATUS_ACTIVE)
        self.contract_product = Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )

    # ── Authentication ──

    def test_returns_401_with_no_authorization_header(self):
        response = self.anon_client.get(self.API_URL, {"account_code": "PH-001"})
        self.assertEqual(response.status_code, 401)

    def test_returns_401_with_invalid_token(self):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Token notavalidtoken")
        self.assertEqual(bad.get(self.API_URL, {"account_code": "PH-001"}).status_code, 401)

    def test_returns_401_with_revoked_token(self):
        revoked = make_api_token(name="Revoked", is_active=False)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION=f"Token {revoked.token}")
        self.assertEqual(bad.get(self.API_URL, {"account_code": "PH-001"}).status_code, 401)

    def test_returns_401_with_malformed_header(self):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.token}")
        self.assertEqual(bad.get(self.API_URL, {"account_code": "PH-001"}).status_code, 401)

    def test_auth_error_follows_error_envelope(self):
        data = self.anon_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"]["code"], "INVALID_TOKEN")

    # ── Parameter validation ──

    def test_returns_400_when_account_code_missing(self):
        self.assertEqual(self.auth_client.get(self.API_URL).status_code, 400)

    def test_400_has_missing_parameter_code(self):
        data = self.auth_client.get(self.API_URL).json()
        self.assertEqual(data["error"]["code"], "MISSING_PARAMETER")

    # ── Business logic errors ──

    def test_returns_404_for_unknown_account(self):
        self.assertEqual(
            self.auth_client.get(self.API_URL, {"account_code": "PH-INVALID"}).status_code, 404
        )

    def test_404_unknown_account_has_correct_code(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-INVALID"}).json()
        self.assertEqual(data["error"]["code"], "ACCOUNT_NOT_FOUND")

    def test_returns_404_when_no_active_contract(self):
        account = make_account(code="PH-002")
        make_contract(account, status=STATUS_INACTIVE)
        self.assertEqual(
            self.auth_client.get(self.API_URL, {"account_code": "PH-002"}).status_code, 404
        )

    def test_404_missing_contract_has_correct_code(self):
        make_account(code="PH-003")
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-003"}).json()
        self.assertEqual(data["error"]["code"], "CONTRACT_NOT_FOUND")

    # ── Success response shape ──

    def test_returns_200_for_valid_request(self):
        self.assertEqual(
            self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).status_code, 200
        )

    def test_success_has_status_success(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(data["status"], "success")

    def test_success_has_timestamp(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertIn("timestamp", data)

    def test_success_has_contract_key(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertIn("contract", data)

    def test_contract_id_matches_active_contract(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(data["contract"]["contract_id"], self.contract.pk)

    def test_contract_title_is_correct(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(data["contract"]["contract_title"], self.contract.title)

    def test_contract_pharmacy_name_is_correct(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(data["contract"]["pharmacy"], "Pharmacie Saada")

    def test_contract_account_code_is_correct(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(data["contract"]["account_code"], "PH-001")

    def test_contract_dates_formatted_as_yyyy_mm_dd(self):
        import re
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(data["contract"]["start_date"], pattern)
        self.assertRegex(data["contract"]["end_date"], pattern)

    def test_last_sale_datetime_is_null_initially(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertIsNone(data["contract"]["last_sale_datetime"])

    def test_last_sync_at_is_null_initially(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertIsNone(data["contract"]["last_sync_at"])

    def test_last_sale_datetime_reflects_accepted_sales(self):
        """After a successful POST /sales/, last_sale_datetime must be updated."""
        self.auth_client.post(
            "/api/v1/sales/",
            {
                "account_code": "PH-001",
                "batch_id":     "BATCH-TEST-001",
                "sales":        [make_sale_row("DOLI1000")],
            },
            format="json",
        )
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertIsNotNone(data["contract"]["last_sale_datetime"])

    def test_product_list_has_correct_length(self):
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(len(data["contract"]["products"]), 1)

    def test_product_entry_has_all_required_fields(self):
        data    = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        product = data["contract"]["products"][0]
        for field in ("product_id", "internal_code", "external_designation", "designation"):
            self.assertIn(field, product)

    def test_product_entry_values_are_correct(self):
        data    = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        product = data["contract"]["products"][0]
        self.assertEqual(product["product_id"],           self.product.pk)
        self.assertEqual(product["internal_code"],        "PROD-001")
        self.assertEqual(product["external_designation"], "DOLI1000")
        self.assertEqual(product["designation"],          "Doliprane 1000")

    def test_returns_empty_products_when_contract_has_none(self):
        account = make_account(code="PH-005")
        make_contract(account, status=STATUS_ACTIVE)
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-005"}).json()
        self.assertEqual(data["contract"]["products"], [])

    def test_returns_all_products_when_multiple(self):
        p2 = make_product(code="PROD-002", designation="Amoxicilline 500mg")
        Contract_Product.objects.create(
            contract=self.contract, product=p2, external_designation="AMOX500"
        )
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        self.assertEqual(len(data["contract"]["products"]), 2)

    # ── Token tracking ──

    def test_usage_count_increments_on_request(self):
        self.auth_client.get(self.API_URL, {"account_code": "PH-001"})
        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, 1)

    def test_last_used_at_set_after_first_request(self):
        self.assertIsNone(self.token.last_used_at)
        self.auth_client.get(self.API_URL, {"account_code": "PH-001"})
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_usage_count_not_incremented_for_invalid_token(self):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Token notavalidtoken")
        bad.get(self.API_URL, {"account_code": "PH-001"})
        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, 0)

    # ── Inactive account (D3a) ──

    def test_returns_404_for_inactive_account(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        self.assertEqual(
            self.auth_client.get(self.API_URL, {"account_code": "PH-INACTIVE"}).status_code, 404
        )

    def test_inactive_account_returns_account_not_found_code(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-INACTIVE"}).json()
        self.assertEqual(data["error"]["code"], "ACCOUNT_NOT_FOUND")

    # ── Response datetime formats (K4, K5) ──

    def test_last_sale_datetime_format_in_response(self):
        """After a sale, last_sale_datetime must be formatted as YYYY-MM-DDTHH:MM:SS."""
        self.auth_client.post(
            "/api/v1/sales/",
            {"account_code": "PH-001", "batch_id": "B-FMT",
             "sales": [make_sale_row("DOLI1000")]},
            format="json",
        )
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        value = data["contract"]["last_sale_datetime"]
        self.assertIsNotNone(value)
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_last_sync_at_format_in_response(self):
        """After a sync, last_sync_at must be formatted as YYYY-MM-DDTHH:MM:SS."""
        self.auth_client.post(
            "/api/v1/contract/sync/",
            {"account_code": "PH-001", "batch_id": "B-FMT"},
            format="json",
        )
        data = self.auth_client.get(self.API_URL, {"account_code": "PH-001"}).json()
        value = data["contract"]["last_sync_at"]
        self.assertIsNotNone(value)
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


# ===========================================================================
# Endpoint 2 — POST /api/v1/sales/
# ===========================================================================

class SalesSubmitViewTests(TestCase):

    API_URL = "/api/v1/sales/"

    def setUp(self):
        cache.clear()
        self.token = make_api_token(name="Sales Token")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.token}")

        self.account  = make_account(code="PH-001")
        self.product  = make_product(code="PROD-001", designation="Doliprane 1000")
        self.contract = make_contract(self.account)
        self.cp       = Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )

    def _post(self, payload):
        return self.client.post(self.API_URL, payload, format="json")

    def _valid_payload(self, batch_id="BATCH-001", rows=None):
        return {
            "account_code": "PH-001",
            "batch_id":     batch_id,
            "sales":        rows if rows is not None else [make_sale_row("DOLI1000")],
        }

    # ── Authentication ──

    def test_returns_401_with_no_token(self):
        anon = APIClient()
        self.assertEqual(anon.post(self.API_URL, {}, format="json").status_code, 401)

    def test_returns_401_with_invalid_token(self):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Token badtoken")
        self.assertEqual(bad.post(self.API_URL, {}, format="json").status_code, 401)

    # ── Request validation ──

    def test_returns_400_when_account_code_missing(self):
        payload = self._valid_payload()
        del payload["account_code"]
        self.assertEqual(self._post(payload).status_code, 400)

    def test_returns_400_when_batch_id_missing(self):
        payload = self._valid_payload()
        del payload["batch_id"]
        self.assertEqual(self._post(payload).status_code, 400)

    def test_returns_400_when_sales_is_empty_list(self):
        payload = self._valid_payload(rows=[])
        self.assertEqual(self._post(payload).status_code, 400)

    def test_returns_400_when_sales_is_not_a_list(self):
        payload = self._valid_payload(rows="not-a-list")
        self.assertEqual(self._post(payload).status_code, 400)

    def test_returns_400_when_row_missing_external_designation(self):
        row = make_sale_row("DOLI1000")
        del row["external_designation"]
        self.assertEqual(self._post(self._valid_payload(rows=[row])).status_code, 400)

    def test_returns_400_when_row_has_invalid_sale_datetime(self):
        row = make_sale_row("DOLI1000")
        row["sale_datetime"] = "not-a-date"
        self.assertEqual(self._post(self._valid_payload(rows=[row])).status_code, 400)

    def test_returns_400_when_batch_too_large(self):
        rows = [make_sale_row("DOLI1000")] * 5001
        self.assertEqual(self._post(self._valid_payload(rows=rows)).status_code, 400)

    def test_400_batch_too_large_has_correct_error_code(self):
        rows = [make_sale_row("DOLI1000")] * 5001
        data = self._post(self._valid_payload(rows=rows)).json()
        self.assertEqual(data["error"]["code"], "BATCH_TOO_LARGE")

    # ── Business logic errors ──

    def test_returns_404_for_unknown_account(self):
        payload = self._valid_payload()
        payload["account_code"] = "PH-UNKNOWN"
        self.assertEqual(self._post(payload).status_code, 404)

    def test_returns_404_when_no_active_contract(self):
        account = make_account(code="PH-002")
        make_contract(account, status=STATUS_INACTIVE)
        payload = self._valid_payload()
        payload["account_code"] = "PH-002"
        self.assertEqual(self._post(payload).status_code, 404)

    # ── Success — response shape ──

    def test_returns_200_for_valid_batch(self):
        self.assertEqual(self._post(self._valid_payload()).status_code, 200)

    def test_response_includes_batch_id(self):
        data = self._post(self._valid_payload("BATCH-XYZ")).json()
        self.assertEqual(data["batch_id"], "BATCH-XYZ")

    def test_response_includes_received_count(self):
        data = self._post(self._valid_payload(rows=[make_sale_row("DOLI1000")] * 3)).json()
        self.assertEqual(data["received"], 3)

    def test_all_valid_rows_accepted(self):
        data = self._post(self._valid_payload(rows=[make_sale_row("DOLI1000")])).json()
        self.assertEqual(data["accepted"], 1)
        self.assertEqual(data["rejected"], 0)
        self.assertEqual(data["errors"], [])

    def test_invalid_external_designation_rejected(self):
        rows = [make_sale_row("DOLI1000"), make_sale_row("UNKNOWN")]
        data = self._post(self._valid_payload(rows=rows)).json()
        self.assertEqual(data["accepted"], 1)
        self.assertEqual(data["rejected"], 1)

    def test_rejected_row_appears_in_errors(self):
        rows = [make_sale_row("UNKNOWN")]
        data = self._post(self._valid_payload(rows=rows)).json()
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["external_designation"], "UNKNOWN")
        self.assertIn("reason", data["errors"][0])
        self.assertIn("index", data["errors"][0])

    def test_row_with_zero_quantity_rejected(self):
        rows = [make_sale_row("DOLI1000", quantity=0)]
        data = self._post(self._valid_payload(rows=rows)).json()
        self.assertEqual(data["rejected"], 1)

    def test_row_with_zero_ppv_rejected(self):
        rows = [make_sale_row("DOLI1000", ppv=0)]
        data = self._post(self._valid_payload(rows=rows)).json()
        self.assertEqual(data["rejected"], 1)

    # ── Success — database state ──

    def test_saleimport_rows_created_in_db(self):
        self._post(self._valid_payload(rows=[make_sale_row("DOLI1000")] * 2))
        self.assertEqual(SaleImport.objects.filter(batch_id="BATCH-001").count(), 2)

    def test_accepted_row_creates_sale_record(self):
        self._post(self._valid_payload(rows=[make_sale_row("DOLI1000")]))
        self.assertEqual(Sale.objects.count(), 1)

    def test_rejected_row_stays_in_saleimport_only(self):
        self._post(self._valid_payload(rows=[make_sale_row("UNKNOWN")]))
        self.assertEqual(SaleImport.objects.filter(status="rejected").count(), 1)
        self.assertEqual(Sale.objects.count(), 0)

    def test_last_sale_datetime_updated_on_contract(self):
        self._post(self._valid_payload(rows=[make_sale_row("DOLI1000")]))
        self.contract.refresh_from_db()
        self.assertIsNotNone(self.contract.last_sale_datetime)

    def test_last_sale_datetime_not_updated_when_all_rejected(self):
        self._post(self._valid_payload(rows=[make_sale_row("UNKNOWN")]))
        self.contract.refresh_from_db()
        self.assertIsNone(self.contract.last_sale_datetime)

    def test_retry_same_batch_does_not_double_count_sales(self):
        """Sending the same batch twice must not create duplicate Sale records."""
        payload = self._valid_payload(rows=[make_sale_row("DOLI1000")])
        self._post(payload)
        self._post(payload)
        self.assertEqual(Sale.objects.count(), 1)

    def test_token_is_stamped_on_saleimport(self):
        self._post(self._valid_payload())
        imp = SaleImport.objects.first()
        self.assertEqual(imp.token, self.token)

    # ── Authentication — missing endpoints (A3b, A4b) ──

    def test_returns_401_with_revoked_token(self):
        revoked = make_api_token(name="Revoked", is_active=False)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION=f"Token {revoked.token}")
        self.assertEqual(bad.post(self.API_URL, self._valid_payload(), format="json").status_code, 401)

    def test_returns_401_with_wrong_auth_scheme(self):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.token}")
        self.assertEqual(bad.post(self.API_URL, self._valid_payload(), format="json").status_code, 401)

    # ── Request format — missing fields (B8, B9, B10) ──

    def test_returns_400_when_row_missing_quantity(self):
        row = make_sale_row("DOLI1000")
        del row["quantity"]
        self.assertEqual(self._post(self._valid_payload(rows=[row])).status_code, 400)

    def test_returns_400_when_row_missing_ppv(self):
        row = make_sale_row("DOLI1000")
        del row["ppv"]
        self.assertEqual(self._post(self._valid_payload(rows=[row])).status_code, 400)

    def test_returns_400_when_row_missing_creation_datetime(self):
        row = make_sale_row("DOLI1000")
        del row["creation_datetime"]
        self.assertEqual(self._post(self._valid_payload(rows=[row])).status_code, 400)

    # ── Request format — whitespace inputs (B11, B12) ──

    def test_returns_400_when_account_code_is_whitespace(self):
        payload = self._valid_payload()
        payload["account_code"] = "   "
        self.assertEqual(self._post(payload).status_code, 400)

    def test_returns_400_when_batch_id_is_whitespace(self):
        payload = self._valid_payload()
        payload["batch_id"] = "   "
        self.assertEqual(self._post(payload).status_code, 400)

    # ── Inactive account (D3b) ──

    def test_returns_404_for_inactive_account(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        payload = self._valid_payload()
        payload["account_code"] = "PH-INACTIVE"
        self.assertEqual(self._post(payload).status_code, 404)

    def test_inactive_account_returns_account_not_found_code(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        payload = self._valid_payload()
        payload["account_code"] = "PH-INACTIVE"
        data = self._post(payload).json()
        self.assertEqual(data["error"]["code"], "ACCOUNT_NOT_FOUND")

    # ── Row-level rejection cases (E2, E4, E6, E7, E8, E9, E10, E11, E12, E13) ──

    def test_product_in_db_but_not_in_contract_is_rejected(self):
        """A product that exists globally but isn't linked to this contract must be rejected."""
        other_product = make_product(code="PROD-OTHER", designation="Amoxicilline")
        # other_product is NOT linked to self.contract
        data = self._post(self._valid_payload(rows=[make_sale_row("PROD-OTHER")])).json()
        self.assertEqual(data["rejected"], 1)

    def test_negative_quantity_is_rejected(self):
        data = self._post(self._valid_payload(rows=[make_sale_row("DOLI1000", quantity=-1)])).json()
        self.assertEqual(data["rejected"], 1)

    def test_negative_ppv_is_rejected(self):
        data = self._post(self._valid_payload(rows=[make_sale_row("DOLI1000", ppv=-5.0)])).json()
        self.assertEqual(data["rejected"], 1)

    def test_sale_before_contract_start_is_rejected(self):
        row = make_sale_row("DOLI1000")
        row["sale_datetime"] = (
            (self.contract.start_date - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        )
        self.assertEqual(self._post(self._valid_payload(rows=[row])).json()["rejected"], 1)

    def test_sale_after_contract_end_is_rejected(self):
        row = make_sale_row("DOLI1000")
        row["sale_datetime"] = (
            (self.contract.end_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        )
        self.assertEqual(self._post(self._valid_payload(rows=[row])).json()["rejected"], 1)

    def test_sale_exactly_on_contract_start_is_accepted(self):
        # Use start_date + 1s to avoid microsecond precision loss from strftime
        row = make_sale_row("DOLI1000")
        dt = (self.contract.start_date + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row["sale_datetime"] = dt
        row["creation_datetime"] = dt
        self.assertEqual(self._post(self._valid_payload(rows=[row])).json()["accepted"], 1)

    def test_sale_exactly_on_contract_end_is_accepted(self):
        # Default end_date is 30 days away — a sale near it would be a future datetime.
        # Move end_date to 1 hour ago, then submit a sale 30 min before that boundary.
        past_end = timezone.now() - timedelta(hours=1)
        Contract.objects.filter(pk=self.contract.pk).update(end_date=past_end)
        row = make_sale_row("DOLI1000")
        dt = (past_end - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
        row["sale_datetime"] = dt
        row["creation_datetime"] = dt
        self.assertEqual(self._post(self._valid_payload(rows=[row])).json()["accepted"], 1)

    def test_future_sale_datetime_is_rejected(self):
        row = make_sale_row("DOLI1000")
        future = (timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        row["sale_datetime"] = future
        row["creation_datetime"] = future
        self.assertEqual(self._post(self._valid_payload(rows=[row])).json()["rejected"], 1)

    def test_creation_datetime_before_sale_datetime_is_rejected(self):
        sale_dt     = (timezone.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        creation_dt = (timezone.now() - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
        row = {
            "external_designation": "DOLI1000",
            "sale_datetime":        sale_dt,
            "creation_datetime":    creation_dt,
            "quantity":             5,
            "ppv":                  12.50,
        }
        self.assertEqual(self._post(self._valid_payload(rows=[row])).json()["rejected"], 1)

    def test_ppv_with_extra_decimal_places_is_accepted_and_stored(self):
        """ppv=12.555 passes the >0 check; DB stores it rounded to 2 decimal places."""
        row = make_sale_row("DOLI1000")
        row["ppv"] = 12.555
        data = self._post(self._valid_payload(rows=[row])).json()
        self.assertEqual(data["accepted"], 1)
        sale = Sale.objects.get()
        self.assertEqual(round(sale.ppv, 2), Decimal("12.56"))

    # ── Batch size boundary (F1) ──

    def test_exactly_max_batch_size_is_accepted(self):
        """MAX_BATCH_SIZE rows must be accepted, not rejected."""
        import sales.services as svc
        with patch.object(svc, "MAX_BATCH_SIZE", 3):
            rows = [make_sale_row("DOLI1000")] * 3
            self.assertEqual(self._post(self._valid_payload(rows=rows)).status_code, 200)

    # ── Database state — max datetime & no-overwrite (G7, G8) ──

    def test_last_sale_datetime_is_max_of_accepted_rows(self):
        now   = timezone.now()
        early = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
        late  = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        rows  = [
            {"external_designation": "DOLI1000", "sale_datetime": early,
             "creation_datetime": early, "quantity": 1, "ppv": 10},
            {"external_designation": "DOLI1000", "sale_datetime": late,
             "creation_datetime": late, "quantity": 1, "ppv": 10},
        ]
        self._post(self._valid_payload(rows=rows))
        self.contract.refresh_from_db()
        self.assertEqual(
            self.contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"), late
        )

    def test_last_sale_datetime_not_overwritten_by_older_batch(self):
        """A second batch with older datetimes must not go backwards."""
        now = timezone.now()
        late  = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        early = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")

        row_late  = {"external_designation": "DOLI1000", "sale_datetime": late,
                     "creation_datetime": late, "quantity": 1, "ppv": 10}
        row_early = {"external_designation": "DOLI1000", "sale_datetime": early,
                     "creation_datetime": early, "quantity": 1, "ppv": 10}

        self._post(self._valid_payload(batch_id="BATCH-001", rows=[row_late]))
        self._post(self._valid_payload(batch_id="BATCH-002", rows=[row_early]))

        self.contract.refresh_from_db()
        self.assertEqual(
            self.contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"), late
        )

    def test_contract_with_zero_products_returns_all_rejected(self):
        account  = make_account(code="PH-EMPTY")
        make_contract(account, status=STATUS_ACTIVE)
        payload = {
            "account_code": "PH-EMPTY",
            "batch_id":     "BATCH-EMPTY",
            "sales":        [make_sale_row("ANYTHING")],
        }
        data = self._post(payload).json()
        self.assertEqual(data["accepted"], 0)
        self.assertEqual(data["rejected"], 1)

    # ── Idempotency — full audit trail (H2, H3, H4, H5) ──

    def test_retry_saleimport_has_two_entries(self):
        """Each submission records in SaleImport even on retry."""
        payload = self._valid_payload(rows=[make_sale_row("DOLI1000")])
        self._post(payload)
        self._post(payload)
        self.assertEqual(SaleImport.objects.filter(batch_id="BATCH-001").count(), 2)

    def test_retry_response_counts_are_correct(self):
        """Second submission of the same batch must return the same accepted/rejected counts."""
        payload = self._valid_payload(rows=[make_sale_row("DOLI1000")])
        first  = self._post(payload).json()
        second = self._post(payload).json()
        self.assertEqual(first["accepted"],  second["accepted"])
        self.assertEqual(first["rejected"],  second["rejected"])

    def test_duplicate_rows_within_batch_create_one_sale(self):
        """Two identical rows in the same request: 2 SaleImports, 1 Sale."""
        row = make_sale_row("DOLI1000")
        self._post(self._valid_payload(rows=[row, row]))
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(SaleImport.objects.count(), 2)

    def test_same_sale_in_two_different_batches_creates_one_sale(self):
        """Same (product + datetime) appearing in BATCH-001 and BATCH-002 → 1 Sale only."""
        row = make_sale_row("DOLI1000")
        self._post(self._valid_payload(batch_id="BATCH-001", rows=[row]))
        self._post(self._valid_payload(batch_id="BATCH-002", rows=[row]))
        self.assertEqual(Sale.objects.count(), 1)

    # ── Multi-batch sequencing (I1, I2) ──

    def test_two_different_batches_both_accepted(self):
        row1 = make_sale_row("DOLI1000", hours_ago=4)
        row2 = make_sale_row("DOLI1000", hours_ago=2)
        self._post(self._valid_payload(batch_id="BATCH-001", rows=[row1]))
        self._post(self._valid_payload(batch_id="BATCH-002", rows=[row2]))
        self.assertEqual(Sale.objects.count(), 2)

    def test_second_batch_with_older_datetimes_does_not_change_last_sale(self):
        now   = timezone.now()
        late  = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        early = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")

        row_late  = {"external_designation": "DOLI1000", "sale_datetime": late,
                     "creation_datetime": late, "quantity": 1, "ppv": 10}
        row_early = {"external_designation": "DOLI1000", "sale_datetime": early,
                     "creation_datetime": early, "quantity": 1, "ppv": 10}

        self._post(self._valid_payload(batch_id="BATCH-001", rows=[row_late]))
        self._post(self._valid_payload(batch_id="BATCH-002", rows=[row_early]))
        self.contract.refresh_from_db()
        self.assertEqual(
            self.contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"), late
        )

    # ── Datetime parsing (K1, K2) ──

    def test_sale_datetime_with_timezone_offset_is_accepted(self):
        """sale_datetime with explicit +00:00 offset must be parsed and accepted."""
        row = make_sale_row("DOLI1000")
        dt_str = (timezone.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        row["sale_datetime"]     = dt_str
        row["creation_datetime"] = dt_str
        data = self._post(self._valid_payload(rows=[row])).json()
        self.assertEqual(data["accepted"], 1)

    def test_sale_datetime_with_z_suffix_is_accepted(self):
        """sale_datetime ending in Z (explicit UTC) must be parsed and accepted."""
        row = make_sale_row("DOLI1000")
        dt_str = (timezone.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row["sale_datetime"]     = dt_str
        row["creation_datetime"] = dt_str
        data = self._post(self._valid_payload(rows=[row])).json()
        self.assertEqual(data["accepted"], 1)

    # ── Atomicity (L1) ──

    def test_atomicity_rollback_on_crash(self):
        """If Sale bulk_create crashes, the whole transaction rolls back — DB stays clean."""
        with patch("sales.services.Sale.objects.bulk_create", side_effect=Exception("DB crash")):
            response = self._post(self._valid_payload())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(SaleImport.objects.count(), 0)
        self.assertEqual(Sale.objects.count(), 0)

    # ── Token tracking (M4, M5) ──

    def test_usage_count_increments_on_post_sales(self):
        self._post(self._valid_payload())
        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, 1)

    def test_last_used_at_set_on_post_sales(self):
        self.assertIsNone(self.token.last_used_at)
        self._post(self._valid_payload())
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    # ── Response shape — error index (N4) ──

    def test_error_index_matches_row_position_in_input(self):
        """In a [valid, invalid] batch, the error entry must have index=1."""
        rows = [make_sale_row("DOLI1000"), make_sale_row("UNKNOWN")]
        data = self._post(self._valid_payload(rows=rows)).json()
        self.assertEqual(data["errors"][0]["index"], 1)


# ===========================================================================
# Endpoint 3 — POST /api/v1/contract/sync/
# ===========================================================================

class ContractSyncViewTests(TestCase):

    API_URL     = "/api/v1/contract/sync/"
    SALES_URL   = "/api/v1/sales/"

    def setUp(self):
        cache.clear()
        self.token = make_api_token(name="Sync Token")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.token}")

        self.account  = make_account(code="PH-001")
        self.product  = make_product(code="PROD-001", designation="Doliprane 1000")
        self.contract = make_contract(self.account)
        Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )

    def _sync(self, account_code="PH-001", batch_id="BATCH-001", last_sale_dt=None):
        payload = {"account_code": account_code, "batch_id": batch_id}
        if last_sale_dt:
            payload["last_sale_datetime"] = last_sale_dt
        return self.client.post(self.API_URL, payload, format="json")

    def _submit_sales(self, rows=None):
        self.client.post(
            self.SALES_URL,
            {
                "account_code": "PH-001",
                "batch_id":     "BATCH-001",
                "sales":        rows if rows is not None else [make_sale_row("DOLI1000")],
            },
            format="json",
        )

    # ── Authentication ──

    def test_returns_401_with_no_token(self):
        anon = APIClient()
        self.assertEqual(anon.post(self.API_URL, {}, format="json").status_code, 401)

    # ── Request validation ──

    def test_returns_400_when_account_code_missing(self):
        self.assertEqual(
            self.client.post(self.API_URL, {"batch_id": "B-001"}, format="json").status_code, 400
        )

    def test_returns_400_when_batch_id_missing(self):
        self.assertEqual(
            self.client.post(self.API_URL, {"account_code": "PH-001"}, format="json").status_code, 400
        )

    # ── Business logic errors ──

    def test_returns_404_for_unknown_account(self):
        self.assertEqual(self._sync(account_code="PH-UNKNOWN").status_code, 404)

    def test_returns_404_when_no_active_contract(self):
        account = make_account(code="PH-002")
        make_contract(account, status=STATUS_INACTIVE)
        self.assertEqual(self._sync(account_code="PH-002").status_code, 404)

    # ── Success — response shape ──

    def test_returns_200_for_valid_request(self):
        self.assertEqual(self._sync().status_code, 200)

    def test_response_includes_contract_id(self):
        data = self._sync().json()
        self.assertEqual(data["contract_id"], self.contract.pk)

    def test_response_includes_last_sync_at(self):
        data = self._sync().json()
        self.assertIn("last_sync_at", data)
        self.assertIsNotNone(data["last_sync_at"])

    def test_response_includes_sync_status(self):
        data = self._sync().json()
        self.assertIn("sync_status", data)

    def test_response_includes_mismatch(self):
        data = self._sync().json()
        self.assertIn("mismatch", data)

    # ── Success — database state ──

    def test_last_sync_at_updated_on_contract(self):
        self.assertIsNone(self.contract.last_sync_at)
        self._sync()
        self.contract.refresh_from_db()
        self.assertIsNotNone(self.contract.last_sync_at)

    # ── Mismatch detection ──

    def test_sync_status_ok_when_datetimes_match(self):
        self._submit_sales()
        self.contract.refresh_from_db()
        reported = self.contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        data = self._sync(last_sale_dt=reported).json()
        self.assertEqual(data["sync_status"], "ok")
        self.assertFalse(data["mismatch"])

    def test_sync_status_warning_when_mismatch(self):
        self._submit_sales()
        data = self._sync(last_sale_dt="2026-01-01T00:00:00").json()
        self.assertEqual(data["sync_status"], "warning")
        self.assertTrue(data["mismatch"])

    def test_detail_present_on_mismatch(self):
        self._submit_sales()
        data = self._sync(last_sale_dt="2026-01-01T00:00:00").json()
        self.assertIn("detail", data)

    def test_detail_absent_on_ok(self):
        self._submit_sales()
        self.contract.refresh_from_db()
        reported = self.contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        data = self._sync(last_sale_dt=reported).json()
        self.assertNotIn("detail", data)

    def test_sync_ok_when_no_last_sale_datetime_sent(self):
        """Sync without last_sale_datetime must default to ok (no cross-check possible)."""
        data = self._sync().json()
        self.assertEqual(data["sync_status"], "ok")

    # ── Authentication — missing (A3c, A4c) ──

    def test_returns_401_with_revoked_token(self):
        revoked = make_api_token(name="Revoked Sync", is_active=False)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION=f"Token {revoked.token}")
        self.assertEqual(
            bad.post(self.API_URL, {"account_code": "PH-001", "batch_id": "B-001"},
                     format="json").status_code, 401
        )

    def test_returns_401_with_wrong_auth_scheme(self):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.token}")
        self.assertEqual(
            bad.post(self.API_URL, {"account_code": "PH-001", "batch_id": "B-001"},
                     format="json").status_code, 401
        )

    # ── Request format — whitespace (C3, C4) ──

    def test_returns_400_when_account_code_is_whitespace(self):
        self.assertEqual(
            self.client.post(self.API_URL,
                             {"account_code": "   ", "batch_id": "B-001"},
                             format="json").status_code, 400
        )

    def test_returns_400_when_batch_id_is_whitespace(self):
        self.assertEqual(
            self.client.post(self.API_URL,
                             {"account_code": "PH-001", "batch_id": "   "},
                             format="json").status_code, 400
        )

    # ── Inactive account (D3c) ──

    def test_returns_404_for_inactive_account(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        self.assertEqual(self._sync(account_code="PH-INACTIVE").status_code, 404)

    def test_inactive_account_returns_account_not_found_code(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        data = self._sync(account_code="PH-INACTIVE").json()
        self.assertEqual(data["error"]["code"], "ACCOUNT_NOT_FOUND")

    # ── Mismatch direction (J4) ──

    def test_sync_warning_when_pharmacy_reports_more_than_we_accepted(self):
        """Pharmacy says 16:00 but we only accepted up to 14:30 — we missed their sales."""
        self._submit_sales()
        future_dt = (timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        data = self._sync(last_sale_dt=future_dt).json()
        self.assertEqual(data["sync_status"], "warning")
        self.assertTrue(data["mismatch"])

    # ── last_sync_at always updates (J8) ──

    def test_last_sync_at_updates_on_second_call(self):
        self._sync()
        self.contract.refresh_from_db()
        first_sync_at = self.contract.last_sync_at

        self._sync()
        self.contract.refresh_from_db()
        second_sync_at = self.contract.last_sync_at

        self.assertGreaterEqual(second_sync_at, first_sync_at)

    # ── Pending warning via API (J9, J10) ──

    def test_pending_warning_in_response_when_batch_has_pending_rows(self):
        SaleImport.objects.create(
            batch_id="BATCH-001", account_code="PH-001",
            external_designation="DOLI1000",
            sale_datetime=timezone.now() - timedelta(hours=1),
            creation_datetime=timezone.now() - timedelta(hours=1),
            quantity=1, ppv=10,
            status=SaleImport.STATUS_PENDING, token=self.token,
        )
        data = self._sync(batch_id="BATCH-001").json()
        self.assertIn("pending_warning", data)
        self.assertEqual(data["sync_status"], "warning")

    def test_no_pending_warning_when_batch_fully_processed(self):
        self._submit_sales(rows=[make_sale_row("DOLI1000")])
        data = self._sync(batch_id="BATCH-001").json()
        self.assertNotIn("pending_warning", data)

    # ── Sync for batch never submitted (J11) ──

    def test_sync_for_unsubmitted_batch_returns_200(self):
        """Sync with a batch_id that was never submitted must still succeed."""
        data = self._sync(batch_id="BATCH-NEVER-SENT").json()
        self.assertEqual(self._sync(batch_id="BATCH-NEVER-SENT").status_code, 200)
        self.assertNotIn("pending_warning", data)

    # ── Sync when no sales yet (J12) ──

    def test_last_sale_datetime_is_null_when_no_sales_submitted(self):
        data = self._sync().json()
        self.assertIsNone(data["last_sale_datetime"])
        self.assertEqual(data["sync_status"], "ok")

    # ── Token tracking (M6) ──

    def test_usage_count_increments_on_post_sync(self):
        self._sync()
        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, 1)


# ===========================================================================
# End-to-End — Multi-pharmacy sync cycles
# ===========================================================================

class PharmacySyncCycleE2ETest(TestCase):
    """
    End-to-end tests simulating real-world pharmacy sync cycles.

    Environment
    -----------
    3 pharmacies, each with its own API token and contract.
    5 products in the internal catalog — shared across pharmacies but
    each pharmacy uses its own external_designation for each product.

    Pharmacies
    ----------
    PH-CASA-001  Pharmacie Atlas, Casablanca   — 3 products (DOLI1000, AMOX500, IBU400)
    PH-RABAT-002 Pharmacie Saada, Rabat        — 3 products (DP-1000, PARA500, VOLT75)
    PH-FES-003   Pharmacie Fès Centre          — 4 products (AMOX-500MG, IBU-400MG,
                                                              PARA-500MG, VOLTARENE75)

    Tests
    -----
    1. Happy path       — Pharmacy 1 submits 6 valid rows across 3 products; sync ok.
    2. Mixed batch      — Pharmacy 2 submits 5 rows (3 valid + 2 bad); sync mismatches.
    3. Retry            — Pharmacy 3 sends the same batch twice; no duplicate Sales.
    4. Data isolation   — Two pharmacies submit concurrently; each sees only its own data.
    """

    CONTRACT_URL = "/api/v1/contract/active/"
    SALES_URL    = "/api/v1/sales/"
    SYNC_URL     = "/api/v1/contract/sync/"

    # ── helpers ────────────────────────────────────────────────────────────

    def _client_for(self, token):
        """Return an APIClient already authenticated with the given token."""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.token}")
        return client

    def _dt(self, hours_ago):
        """Return a naive ISO-8601 string N hours in the past."""
        return (timezone.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S")

    def _row(self, designation, hours_ago, quantity, ppv):
        dt = self._dt(hours_ago)
        return {
            "external_designation": designation,
            "sale_datetime":        dt,
            "creation_datetime":    dt,
            "quantity":             quantity,
            "ppv":                  ppv,
        }

    # ── setUp ──────────────────────────────────────────────────────────────

    def setUp(self):
        cache.clear()

        # ── 5 products in the internal FIDPHA catalog ──
        self.doliprane_1000 = make_product(code="PROD-D1000", designation="Doliprane 1000mg")
        self.amox_500       = make_product(code="PROD-A500",  designation="Amoxicilline 500mg")
        self.ibu_400        = make_product(code="PROD-I400",  designation="Ibuprofène 400mg")
        self.para_500       = make_product(code="PROD-P500",  designation="Paracétamol 500mg")
        self.voltaren_75    = make_product(code="PROD-V75",   designation="Voltarène 75mg")

        # ── Pharmacy 1 — Pharmacie Atlas, Casablanca ──
        self.account_1  = make_account(code="PH-CASA-001",  name="Pharmacie Atlas")
        self.token_1    = make_api_token(name="Token Atlas")
        self.contract_1 = make_contract(self.account_1)
        Contract_Product.objects.create(
            contract=self.contract_1, product=self.doliprane_1000,
            external_designation="DOLI1000",
        )
        Contract_Product.objects.create(
            contract=self.contract_1, product=self.amox_500,
            external_designation="AMOX500",
        )
        Contract_Product.objects.create(
            contract=self.contract_1, product=self.ibu_400,
            external_designation="IBU400",
        )

        # ── Pharmacy 2 — Pharmacie Saada, Rabat ──
        # Same internal products as pharmacy 1 but different external designations —
        # each pharmacy uses its own naming conventions in its POS system.
        self.account_2  = make_account(code="PH-RABAT-002", name="Pharmacie Saada")
        self.token_2    = make_api_token(name="Token Saada")
        self.contract_2 = make_contract(self.account_2)
        Contract_Product.objects.create(
            contract=self.contract_2, product=self.doliprane_1000,
            external_designation="DP-1000",
        )
        Contract_Product.objects.create(
            contract=self.contract_2, product=self.para_500,
            external_designation="PARA500",
        )
        Contract_Product.objects.create(
            contract=self.contract_2, product=self.voltaren_75,
            external_designation="VOLT75",
        )

        # ── Pharmacy 3 — Pharmacie Fès Centre ──
        self.account_3  = make_account(code="PH-FES-003",   name="Pharmacie Fes Centre")
        self.token_3    = make_api_token(name="Token Fes")
        self.contract_3 = make_contract(self.account_3)
        Contract_Product.objects.create(
            contract=self.contract_3, product=self.amox_500,
            external_designation="AMOX-500MG",
        )
        Contract_Product.objects.create(
            contract=self.contract_3, product=self.ibu_400,
            external_designation="IBU-400MG",
        )
        Contract_Product.objects.create(
            contract=self.contract_3, product=self.para_500,
            external_designation="PARA-500MG",
        )
        Contract_Product.objects.create(
            contract=self.contract_3, product=self.voltaren_75,
            external_designation="VOLTARENE75",
        )

    # ── Test 1 — Happy path: all products, all accepted ────────────────────

    def test_pharmacy_1_happy_path_all_products(self):
        """
        Pharmacie Atlas sends 6 sales covering all 3 of its products
        spread across 6 different datetimes.

        Step 1: GET /contract/active/ → read product map from response (not hardcoded).
        Step 2: POST /sales/          → all 6 rows accepted, last_sale_datetime = max.
        Step 3: POST /contract/sync/  → pharmacy reports the same max → sync_status ok.
        """
        client = self._client_for(self.token_1)

        # ── Step 1 ────────────────────────────────────────────────────────
        r1 = client.get(self.CONTRACT_URL, {"account_code": "PH-CASA-001"})
        self.assertEqual(r1.status_code, 200)

        products   = r1.json()["contract"]["products"]
        ext_by_des = {p["external_designation"]: p for p in products}

        # All 3 designations must be discoverable from the response
        self.assertIn("DOLI1000", ext_by_des)
        self.assertIn("AMOX500",  ext_by_des)
        self.assertIn("IBU400",   ext_by_des)

        # Internal codes returned must match the catalog
        self.assertEqual(ext_by_des["DOLI1000"]["internal_code"], "PROD-D1000")
        self.assertEqual(ext_by_des["AMOX500"]["internal_code"],  "PROD-A500")
        self.assertEqual(ext_by_des["IBU400"]["internal_code"],   "PROD-I400")

        # ── Step 2 ────────────────────────────────────────────────────────
        batch_id = "ATLAS-BATCH-20260419-001"
        # 6 rows — two per product, spread across 6 hours
        rows = [
            self._row("DOLI1000", hours_ago=6, quantity=3,  ppv=12.50),
            self._row("AMOX500",  hours_ago=5, quantity=1,  ppv=32.00),
            self._row("IBU400",   hours_ago=4, quantity=2,  ppv=8.75),
            self._row("DOLI1000", hours_ago=3, quantity=5,  ppv=12.50),
            self._row("AMOX500",  hours_ago=2, quantity=2,  ppv=32.00),
            self._row("IBU400",   hours_ago=1, quantity=1,  ppv=8.75),
        ]
        late_dt = self._dt(hours_ago=1)  # the most recent row — expected max

        r2 = client.post(
            self.SALES_URL,
            {"account_code": "PH-CASA-001", "batch_id": batch_id, "sales": rows},
            format="json",
        )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()

        self.assertEqual(d2["received"], 6)
        self.assertEqual(d2["accepted"], 6)
        self.assertEqual(d2["rejected"], 0)
        self.assertEqual(d2["errors"],   [])

        # 6 Sale records in the database
        self.assertEqual(Sale.objects.count(), 6)

        # last_sale_datetime = max of the 6 rows = 1 hour ago
        self.contract_1.refresh_from_db()
        self.assertEqual(
            self.contract_1.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            late_dt,
        )

        # ── Step 3 ────────────────────────────────────────────────────────
        r3 = client.post(
            self.SYNC_URL,
            {"account_code": "PH-CASA-001", "batch_id": batch_id,
             "last_sale_datetime": late_dt},
            format="json",
        )
        self.assertEqual(r3.status_code, 200)
        d3 = r3.json()

        self.assertEqual(d3["sync_status"], "ok")
        self.assertFalse(d3["mismatch"])
        self.assertNotIn("detail",          d3)
        self.assertNotIn("pending_warning", d3)
        self.assertEqual(d3["last_sale_datetime"], late_dt)

        self.contract_1.refresh_from_db()
        self.assertIsNotNone(self.contract_1.last_sync_at)

    # ── Test 2 — Mixed batch + mismatch on sync ────────────────────────────

    def test_pharmacy_2_mixed_batch_then_mismatch_on_sync(self):
        """
        Pharmacie Saada sends 5 rows:
          - 3 valid (DP-1000, PARA500, VOLT75 — all in their contract)
          - 1 using pharmacy 1's designation DOLI1000 (not in pharmacy 2's contract)
          - 1 completely unknown designation

        The pharmacy then reports the max datetime of ALL 5 rows (including the 2
        rejected ones) → sync detects a mismatch because we only accepted up to
        the max of the 3 valid rows.
        """
        client = self._client_for(self.token_2)

        # ── Step 1 ────────────────────────────────────────────────────────
        r1 = client.get(self.CONTRACT_URL, {"account_code": "PH-RABAT-002"})
        self.assertEqual(r1.status_code, 200)

        products   = r1.json()["contract"]["products"]
        ext_by_des = {p["external_designation"]: p for p in products}

        # Pharmacy 2's designations must be present
        self.assertIn("DP-1000", ext_by_des)
        self.assertIn("PARA500", ext_by_des)
        self.assertIn("VOLT75",  ext_by_des)

        # Pharmacy 1's designations must NOT appear — different contract
        self.assertNotIn("DOLI1000", ext_by_des)
        self.assertNotIn("AMOX500",  ext_by_des)
        self.assertNotIn("IBU400",   ext_by_des)

        # ── Step 2 ────────────────────────────────────────────────────────
        batch_id = "SAADA-BATCH-20260419-001"
        rows = [
            self._row("DP-1000",  hours_ago=5, quantity=4, ppv=12.50),  # valid
            self._row("PARA500",  hours_ago=4, quantity=2, ppv=6.00),   # valid
            self._row("VOLT75",   hours_ago=3, quantity=1, ppv=24.00),  # valid — max accepted
            self._row("DOLI1000", hours_ago=2, quantity=2, ppv=12.50),  # INVALID — pharmacy 1 only
            self._row("UNKNOWN",  hours_ago=1, quantity=1, ppv=5.00),   # INVALID — does not exist
        ]

        r2 = client.post(
            self.SALES_URL,
            {"account_code": "PH-RABAT-002", "batch_id": batch_id, "sales": rows},
            format="json",
        )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()

        self.assertEqual(d2["received"], 5)
        self.assertEqual(d2["accepted"], 3)
        self.assertEqual(d2["rejected"], 2)
        self.assertEqual(len(d2["errors"]), 2)

        # Rejected rows are at index 3 and 4
        rejected_indices = {e["index"] for e in d2["errors"]}
        self.assertEqual(rejected_indices, {3, 4})

        # Only 3 Sale records in the database — the 2 bad rows never reach Sale
        self.assertEqual(Sale.objects.count(), 3)

        # last_sale_datetime = max of ACCEPTED rows only = 3 hours ago (VOLT75)
        self.contract_2.refresh_from_db()
        self.assertEqual(
            self.contract_2.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            self._dt(hours_ago=3),
        )

        # ── Step 3 — pharmacy reports including rejected rows → mismatch ──
        # The pharmacy's POS system does not know about our rejections.
        # It reports the last datetime it saw locally: 1 hour ago (the UNKNOWN row).
        # We only accepted up to 3 hours ago → mismatch.
        reported_dt = self._dt(hours_ago=1)

        r3 = client.post(
            self.SYNC_URL,
            {"account_code": "PH-RABAT-002", "batch_id": batch_id,
             "last_sale_datetime": reported_dt},
            format="json",
        )
        self.assertEqual(r3.status_code, 200)
        d3 = r3.json()

        self.assertEqual(d3["sync_status"], "warning")
        self.assertTrue(d3["mismatch"])
        self.assertIn("detail", d3)  # explanation must be present on mismatch

        # last_sale_datetime in the response is what WE accepted (3 hours ago)
        self.assertEqual(
            d3["last_sale_datetime"],
            self._dt(hours_ago=3),
        )

    # ── Test 3 — Network retry: same batch sent twice ──────────────────────

    def test_pharmacy_3_retry_does_not_duplicate_sales(self):
        """
        Pharmacie Fès sends a batch, gets a network timeout, and resends
        the exact same batch. The system must be idempotent:
          - 2 SaleImport rows per original row (full audit trail of both submissions)
          - Only 1 Sale row per original row (no duplicate counting)
        """
        client = self._client_for(self.token_3)

        batch_id = "FES-BATCH-20260419-001"
        rows = [
            self._row("AMOX-500MG",  hours_ago=4, quantity=3, ppv=32.00),
            self._row("IBU-400MG",   hours_ago=3, quantity=1, ppv=8.75),
            self._row("PARA-500MG",  hours_ago=2, quantity=2, ppv=6.00),
            self._row("VOLTARENE75", hours_ago=1, quantity=1, ppv=24.00),
        ]
        late_dt = self._dt(hours_ago=1)

        # ── First submission ───────────────────────────────────────────────
        r2a = client.post(
            self.SALES_URL,
            {"account_code": "PH-FES-003", "batch_id": batch_id, "sales": rows},
            format="json",
        )
        self.assertEqual(r2a.status_code, 200)
        self.assertEqual(r2a.json()["accepted"], 4)
        self.assertEqual(r2a.json()["rejected"], 0)

        # ── Second submission — same batch_id, same rows (network retry) ──
        r2b = client.post(
            self.SALES_URL,
            {"account_code": "PH-FES-003", "batch_id": batch_id, "sales": rows},
            format="json",
        )
        self.assertEqual(r2b.status_code, 200)
        # Validation still passes — rows are individually valid
        self.assertEqual(r2b.json()["accepted"], 4)
        self.assertEqual(r2b.json()["rejected"], 0)

        # Sale table: 4 unique records — duplicates silently skipped
        self.assertEqual(Sale.objects.count(), 4)

        # SaleImport table: 8 rows — both submissions fully recorded for audit
        self.assertEqual(
            SaleImport.objects.filter(batch_id=batch_id).count(), 8,
        )

        # last_sale_datetime must not change on the second submission
        # (it was already at late_dt from the first one)
        self.contract_3.refresh_from_db()
        self.assertEqual(
            self.contract_3.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            late_dt,
        )

        # ── Step 3 — sync after retry: ok, no pending rows ────────────────
        r3 = client.post(
            self.SYNC_URL,
            {"account_code": "PH-FES-003", "batch_id": batch_id,
             "last_sale_datetime": late_dt},
            format="json",
        )
        self.assertEqual(r3.status_code, 200)
        d3 = r3.json()
        self.assertEqual(d3["sync_status"], "ok")
        self.assertFalse(d3["mismatch"])
        self.assertNotIn("pending_warning", d3)

    # ── Test 4 — Data isolation between pharmacies ─────────────────────────

    def test_cross_pharmacy_data_isolation(self):
        """
        Pharmacy 1 and Pharmacy 2 submit sales concurrently.
        Their data must be completely isolated:
          - Each contract has its own Sale records.
          - last_sale_datetime is tracked independently per contract.
          - Pharmacy 1 cannot use Pharmacy 2's external_designations (and vice versa).
        """
        client_1 = self._client_for(self.token_1)
        client_2 = self._client_for(self.token_2)

        # ── Pharmacy 1 submits 2 sales (max = 2 hours ago) ────────────────
        r_ph1 = client_1.post(
            self.SALES_URL,
            {
                "account_code": "PH-CASA-001",
                "batch_id":     "ATLAS-ISO-001",
                "sales": [
                    self._row("DOLI1000", hours_ago=4, quantity=2, ppv=12.50),
                    self._row("IBU400",   hours_ago=2, quantity=1, ppv=8.75),
                ],
            },
            format="json",
        )
        self.assertEqual(r_ph1.json()["accepted"], 2)

        # ── Pharmacy 2 submits 3 sales (max = 1 hour ago) ─────────────────
        r_ph2 = client_2.post(
            self.SALES_URL,
            {
                "account_code": "PH-RABAT-002",
                "batch_id":     "SAADA-ISO-001",
                "sales": [
                    self._row("DP-1000", hours_ago=5, quantity=4, ppv=12.50),
                    self._row("PARA500", hours_ago=3, quantity=2, ppv=6.00),
                    self._row("VOLT75",  hours_ago=1, quantity=1, ppv=24.00),
                ],
            },
            format="json",
        )
        self.assertEqual(r_ph2.json()["accepted"], 3)

        # ── Total DB state ─────────────────────────────────────────────────
        self.assertEqual(Sale.objects.count(), 5)

        # Each contract owns only its Sales — data does not bleed across
        self.assertEqual(
            Sale.objects.filter(contract_product__contract=self.contract_1).count(), 2,
        )
        self.assertEqual(
            Sale.objects.filter(contract_product__contract=self.contract_2).count(), 3,
        )

        # last_sale_datetime is tracked independently
        self.contract_1.refresh_from_db()
        self.contract_2.refresh_from_db()

        # Pharmacy 1 max = 2 hours ago; Pharmacy 2 max = 1 hour ago
        self.assertGreater(
            self.contract_2.last_sale_datetime,
            self.contract_1.last_sale_datetime,
            "Pharmacy 2's last_sale_datetime should be more recent than Pharmacy 1's",
        )

        # ── Cross-designation rejection ────────────────────────────────────
        # Pharmacy 1 tries to use DP-1000 — which is Pharmacy 2's designation
        # for Doliprane. It should be rejected because it does not exist in
        # Pharmacy 1's Contract_Product table.
        r_cross = client_1.post(
            self.SALES_URL,
            {
                "account_code": "PH-CASA-001",
                "batch_id":     "ATLAS-CROSS-ATTEMPT",
                "sales": [
                    self._row("DP-1000", hours_ago=1, quantity=1, ppv=12.50),
                ],
            },
            format="json",
        )
        self.assertEqual(r_cross.json()["accepted"], 0)
        self.assertEqual(r_cross.json()["rejected"], 1,
            "DP-1000 belongs to pharmacy 2 only — must be rejected for pharmacy 1"
        )

    # ── Test 5 — Bulk: 1000 products, 1000-row batch ───────────────────────

    def test_bulk_1000_products_single_pharmacy(self):
        """
        A dedicated pharmacy with 1000 products submits a 1000-row batch
        in a single POST /sales/ call.

        What this proves that smaller tests cannot:
          - cp_map pre-fetch works at scale: one DB query fetches all 1000
            Contract_Product rows — not 1000 individual lookups (no N+1).
          - bulk_create handles 1000 SaleImport rows in a single INSERT.
          - bulk_create handles 1000 Sale rows in a single INSERT.
          - last_sale_datetime = max of 1000 rows, correctly identified.
          - GET /contract/active/ lists all 1000 products without truncation.
          - POST /contract/sync/ confirms ok on a 1000-row batch.
        """
        N = 1000

        # ── Build a dedicated bulk pharmacy ───────────────────────────────
        bulk_account  = make_account(code="PH-BULK-001", name="Pharmacie Bulk Test")
        bulk_token    = make_api_token(name="Token Bulk")
        bulk_contract = make_contract(bulk_account)
        client        = self._client_for(bulk_token)

        # Bulk-create 1000 products in one query
        products = Product.objects.bulk_create([
            Product(
                code=f"BULK-{i:04d}",
                designation=f"Bulk Product {i:04d}",
                status=STATUS_ACTIVE,
            )
            for i in range(N)
        ])

        # Bulk-create 1000 Contract_Product links in one query.
        # Each pharmacy uses its own external designation — here "EXT-0000"…"EXT-0999".
        Contract_Product.objects.bulk_create([
            Contract_Product(
                contract=bulk_contract,
                product=p,
                external_designation=f"EXT-{i:04d}",
            )
            for i, p in enumerate(products)
        ])

        # ── Step 1: GET /contract/active/ ─────────────────────────────────
        r1 = client.get(self.CONTRACT_URL, {"account_code": "PH-BULK-001"})
        self.assertEqual(r1.status_code, 200)

        response_products = r1.json()["contract"]["products"]

        # All 1000 products must be listed
        self.assertEqual(len(response_products), N)

        # Every external designation must be present — set comparison is O(N)
        returned_ext = {p["external_designation"] for p in response_products}
        expected_ext = {f"EXT-{i:04d}" for i in range(N)}
        self.assertEqual(returned_ext, expected_ext)

        # ── Step 2: POST /sales/ — 1000 rows ──────────────────────────────
        # Rows 0–998 share the same sale_datetime (2 hours ago).
        # Row 999 is 1 hour ago — the clear max across the whole batch.
        # Using the same datetime for 998 rows is fine because unique_together
        # is (contract_product, sale_datetime), and every row has a different
        # contract_product.
        now      = timezone.now()
        base_dt  = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        max_dt   = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        rows = [
            {
                "external_designation": f"EXT-{i:04d}",
                "sale_datetime":        max_dt if i == N - 1 else base_dt,
                "creation_datetime":    max_dt if i == N - 1 else base_dt,
                "quantity":             (i % 5) + 1,   # 1–5, realistic variation
                "ppv":                  round(10 + (i % 20) * 0.5, 2),  # 10.00–19.50
            }
            for i in range(N)
        ]

        batch_id = "BULK-BATCH-001"
        r2 = client.post(
            self.SALES_URL,
            {"account_code": "PH-BULK-001", "batch_id": batch_id, "sales": rows},
            format="json",
        )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()

        # Every row must be accepted — all 1000 designations exist in the contract
        self.assertEqual(d2["received"], N)
        self.assertEqual(d2["accepted"], N)
        self.assertEqual(d2["rejected"], 0)
        self.assertEqual(d2["errors"],   [])

        # Exactly 1000 Sale records in the database
        self.assertEqual(
            Sale.objects.filter(contract_product__contract=bulk_contract).count(), N,
        )

        # last_sale_datetime must be the max row — EXT-0999, 1 hour ago
        bulk_contract.refresh_from_db()
        self.assertEqual(
            bulk_contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            max_dt,
            "last_sale_datetime must be the single latest row (EXT-0999), not any of the 999 earlier rows",
        )

        # ── Step 3: POST /contract/sync/ ──────────────────────────────────
        # Pharmacy reports its own max (max_dt) → must match what we accepted
        r3 = client.post(
            self.SYNC_URL,
            {
                "account_code":       "PH-BULK-001",
                "batch_id":           batch_id,
                "last_sale_datetime": max_dt,
            },
            format="json",
        )
        self.assertEqual(r3.status_code, 200)
        d3 = r3.json()

        self.assertEqual(d3["sync_status"], "ok")
        self.assertFalse(d3["mismatch"])
        self.assertNotIn("detail",          d3)
        self.assertNotIn("pending_warning", d3)
        self.assertEqual(d3["last_sale_datetime"], max_dt)

        # last_sync_at stamped on the contract
        bulk_contract.refresh_from_db()
        self.assertIsNotNone(bulk_contract.last_sync_at)


# ===========================================================================
# Concurrent submissions — TransactionTestCase
# ===========================================================================

@unittest.skipIf(
    _USING_SQLITE,
    "SQLite shared-cache in-memory mode raises SQLITE_LOCKED on concurrent "
    "table writes — busy_timeout only handles SQLITE_BUSY (file-level locks). "
    "Re-enable these tests with PostgreSQL.",
)
class PharmacyConcurrentSubmissionTest(TransactionTestCase):
    """
    Tests concurrent batch submissions using real OS threads.

    Why TransactionTestCase and not TestCase?
    -----------------------------------------
    TestCase wraps every test in a single transaction that never commits.
    Threads spawned inside a TestCase share that transaction and cannot see
    each other's writes — concurrent tests would be meaningless.
    TransactionTestCase commits each write to the DB, so threads interact
    with real shared state, exactly as in production.

    What these tests prove
    ----------------------
    1. Five pharmacies submitting simultaneously produce no data leakage —
       each contract's Sales are isolated even under concurrent load.

    2. The same pharmacy submitting two concurrent batches never corrupts
       last_sale_datetime — select_for_update() + transaction.atomic()
       serialise the writes so the final value is always the global max,
       regardless of which thread wins the DB lock first.

    SQLite note
    -----------
    SQLite shared-cache in-memory mode (used by Django's test runner) uses
    table-level locks and raises SQLITE_LOCKED immediately when two threads
    write to the same table. busy_timeout cannot help — it only retries on
    SQLITE_BUSY (file-level locks). Run with PostgreSQL to enable these tests.
    """

    SALES_URL = "/api/v1/sales/"

    def setUp(self):
        cache.clear()

    # ── helpers ────────────────────────────────────────────────────────────

    def _client_for(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.token}")
        return client

    # ── Test 1 — 5 pharmacies, all submitting at the same time ─────────────

    def test_five_pharmacies_submit_simultaneously(self):
        """
        Five pharmacies each submit a 10-row batch from separate threads,
        all started at the same instant.

        Asserts:
        - Every pharmacy's response shows accepted=10, rejected=0.
        - Total Sale.count() == 50 (5 × 10) — no rows lost or doubled.
        - Each contract owns exactly 10 Sale records — no cross-contamination.
        - Every contract.last_sale_datetime is set (1 hour ago = max of 10 rows).
        - No thread raises an exception.
        """
        PHARMACY_COUNT    = 5
        ROWS_PER_PHARMACY = 10

        # ── Build 5 pharmacies with 10 products each ──────────────────────
        # Capture a shared `now` so all datetimes are computed consistently
        # across threads — avoids off-by-one-second failures on slow machines.
        now = timezone.now()

        pharmacies = []
        for i in range(PHARMACY_COUNT):
            account  = make_account(
                code=f"PH-CONC-{i:03d}",
                name=f"Pharmacie Concurrent {i}",
            )
            token    = make_api_token(name=f"Token Concurrent {i}")
            contract = make_contract(account)

            products = Product.objects.bulk_create([
                Product(
                    code=f"CONC-{i:03d}-P{j:02d}",
                    designation=f"Product {i}-{j}",
                    status=STATUS_ACTIVE,
                )
                for j in range(ROWS_PER_PHARMACY)
            ])
            Contract_Product.objects.bulk_create([
                Contract_Product(
                    contract=contract,
                    product=p,
                    external_designation=f"CONC-{i:03d}-E{j:02d}",
                )
                for j, p in enumerate(products)
            ])
            pharmacies.append((account, token, contract))

        # Precompute datetimes:
        # Row j gets sale_datetime = now - (j+1) hours
        # Row 0 is 1 hour ago → it is the max for every pharmacy
        max_dt = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        # ── Thread worker ──────────────────────────────────────────────────
        results = {}   # account_code → response JSON
        errors  = []
        lock    = threading.Lock()

        def submit(idx, account, token):
            try:
                client = self._client_for(token)
                rows = [
                    {
                        "external_designation": f"CONC-{idx:03d}-E{j:02d}",
                        "sale_datetime":        (now - timedelta(hours=j + 1)).strftime("%Y-%m-%dT%H:%M:%S"),
                        "creation_datetime":    (now - timedelta(hours=j + 1)).strftime("%Y-%m-%dT%H:%M:%S"),
                        "quantity":             j + 1,
                        "ppv":                  round(10.00 + j * 0.5, 2),
                    }
                    for j in range(ROWS_PER_PHARMACY)
                ]
                r = client.post(
                    self.SALES_URL,
                    {
                        "account_code": account.code,
                        "batch_id":     f"BATCH-CONC-{idx:03d}",
                        "sales":        rows,
                    },
                    format="json",
                )
                with lock:
                    results[account.code] = r.json()
            except Exception as exc:
                with lock:
                    errors.append(f"Pharmacy {idx}: {exc}")

        # ── Launch all threads simultaneously ──────────────────────────────
        threads = [
            threading.Thread(target=submit, args=(i, account, token))
            for i, (account, token, contract) in enumerate(pharmacies)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # ── Assertions ─────────────────────────────────────────────────────

        # No thread crashed
        self.assertEqual(errors, [], f"Thread errors: {errors}")

        # All 5 responses received
        self.assertEqual(len(results), PHARMACY_COUNT)

        # Every pharmacy: all 10 rows accepted
        for code, data in results.items():
            self.assertEqual(data["received"], ROWS_PER_PHARMACY, f"{code}: wrong received")
            self.assertEqual(data["accepted"], ROWS_PER_PHARMACY, f"{code}: wrong accepted")
            self.assertEqual(data["rejected"], 0,                 f"{code}: unexpected rejections")

        # Total Sales in the DB = 5 × 10 = 50
        self.assertEqual(Sale.objects.count(), PHARMACY_COUNT * ROWS_PER_PHARMACY)

        # Each contract owns exactly 10 Sales — zero cross-contamination
        for i, (account, token, contract) in enumerate(pharmacies):
            self.assertEqual(
                Sale.objects.filter(contract_product__contract=contract).count(),
                ROWS_PER_PHARMACY,
                f"Pharmacy {i} has wrong Sale count",
            )
            contract.refresh_from_db()
            self.assertEqual(
                contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
                max_dt,
                f"Pharmacy {i} last_sale_datetime should be the max row (1 hour ago)",
            )

    # ── Test 2 — Same contract, two concurrent batches ─────────────────────

    def test_same_contract_two_concurrent_batches(self):
        """
        The same pharmacy submits two different batches from two threads
        at the same instant.

        BATCH-A  →  product RACE-A, sale 3 hours ago
        BATCH-B  →  product RACE-B, sale 1 hour ago  ← the global max

        Both threads compete for the select_for_update() lock on the same
        contract row. One blocks until the other commits, then proceeds.

        Regardless of which thread wins the lock:
        - Both Sale records must be created (2 total).
        - last_sale_datetime must end up at 1 hour ago (the global max).

        Why last_sale_datetime is always correct:
          Thread that runs first  → sets last_sale_datetime to its max.
          Thread that runs second → reads the updated value and only
                                    overwrites it if its max is higher.
          The update is: if max_sale_dt > contract.last_sale_datetime: update.
          So whichever order they run, the final value is always the overall max.
        """
        now  = timezone.now()
        dt_3h = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        dt_1h = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        account  = make_account(code="PH-RACE-001", name="Pharmacie Race Test")
        token    = make_api_token(name="Token Race")
        contract = make_contract(account)

        prod_a = make_product(code="RACE-PROD-A", designation="Race Product A")
        prod_b = make_product(code="RACE-PROD-B", designation="Race Product B")
        Contract_Product.objects.create(
            contract=contract, product=prod_a, external_designation="RACE-A",
        )
        Contract_Product.objects.create(
            contract=contract, product=prod_b, external_designation="RACE-B",
        )

        results = {}
        errors  = []
        lock    = threading.Lock()

        def submit_batch(batch_id, designation, sale_dt):
            try:
                client = self._client_for(token)
                r = client.post(
                    self.SALES_URL,
                    {
                        "account_code": "PH-RACE-001",
                        "batch_id":     batch_id,
                        "sales": [{
                            "external_designation": designation,
                            "sale_datetime":        sale_dt,
                            "creation_datetime":    sale_dt,
                            "quantity": 1, "ppv": 10.00,
                        }],
                    },
                    format="json",
                )
                with lock:
                    results[batch_id] = r.json()
            except Exception as exc:
                with lock:
                    errors.append(f"{batch_id}: {exc}")

        thread_a = threading.Thread(
            target=submit_batch, args=("BATCH-A", "RACE-A", dt_3h)
        )
        thread_b = threading.Thread(
            target=submit_batch, args=("BATCH-B", "RACE-B", dt_1h)
        )

        # Start both threads at the same time
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=30)
        thread_b.join(timeout=30)

        # No thread crashed
        self.assertEqual(errors, [], f"Thread errors: {errors}")

        # Both batches accepted
        self.assertEqual(results["BATCH-A"]["accepted"], 1)
        self.assertEqual(results["BATCH-B"]["accepted"], 1)

        # 2 Sale records — one from each batch
        self.assertEqual(Sale.objects.count(), 2)

        # last_sale_datetime = 1 hour ago (the global max across both batches)
        # This holds true regardless of which thread ran first.
        contract.refresh_from_db()
        self.assertEqual(
            contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            dt_1h,
            "last_sale_datetime must be the global max (1 hour ago) "
            "regardless of which batch acquired the DB lock first",
        )
