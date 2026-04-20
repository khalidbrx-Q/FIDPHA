"""
sales/tests.py
--------------
Service-layer tests for the sales app.

Tests submit_sales_batch() and confirm_sync() directly — no HTTP involved.
These tests cover edge cases that are harder to trigger via the API layer,
such as the idempotency guard, the pending-row warning, and date boundary
validation.

How to run:
    python manage.py test sales
    python manage.py test sales.tests.SubmitSalesBatchTests
    python manage.py test sales.tests.ConfirmSyncTests

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from api.models import APIToken
from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    AccountNotFoundError,
    ContractNotFoundError,
)
from sales.models import Sale, SaleImport
from sales.services import (
    BatchTooLargeError,
    MAX_BATCH_SIZE,
    confirm_sync,
    submit_sales_batch,
)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_account(code="PH-TEST", status=STATUS_ACTIVE):
    return Account.objects.create(
        code=code, name="Test Pharmacy",
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


def make_token(name="Test Token"):
    return APIToken.objects.create(name=name, is_active=True)


def make_row(ext="DOLI1000", hours_ago=2, quantity=5, ppv=12.50):
    """Return a valid sale row dict (datetimes already parsed as datetime objects)."""
    dt = timezone.now() - timedelta(hours=hours_ago)
    return {
        "external_designation": ext,
        "sale_datetime":        dt,
        "creation_datetime":    dt,
        "quantity":             quantity,
        "ppv":                  ppv,
    }


# ===========================================================================
# submit_sales_batch()
# ===========================================================================

class SubmitSalesBatchTests(TestCase):

    def setUp(self):
        self.token    = make_token()
        self.account  = make_account()
        self.product  = make_product()
        self.contract = make_contract(self.account)
        self.cp       = Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )

    def _submit(self, rows=None, batch_id="BATCH-001", account_code="PH-TEST"):
        return submit_sales_batch(
            account_code=account_code,
            batch_id=batch_id,
            sales_data=rows or [make_row()],
            token=self.token,
        )

    # ── Validation / errors ──

    def test_raises_batch_too_large_error(self):
        with self.assertRaises(BatchTooLargeError):
            self._submit(rows=[make_row()] * (MAX_BATCH_SIZE + 1))

    def test_raises_account_not_found(self):
        with self.assertRaises(AccountNotFoundError):
            self._submit(account_code="PH-UNKNOWN")

    def test_raises_contract_not_found_for_inactive_contract(self):
        account = make_account(code="PH-002")
        make_contract(account, status=STATUS_INACTIVE)
        with self.assertRaises(ContractNotFoundError):
            self._submit(account_code="PH-002")

    # ── Return value ──

    def test_returns_dict_with_expected_keys(self):
        result = self._submit()
        for key in ("batch_id", "received", "accepted", "rejected", "errors"):
            self.assertIn(key, result)

    def test_batch_id_matches_input(self):
        self.assertEqual(self._submit(batch_id="MY-BATCH")["batch_id"], "MY-BATCH")

    def test_received_equals_number_of_rows(self):
        self.assertEqual(self._submit(rows=[make_row()] * 3)["received"], 3)

    # ── Happy path ──

    def test_all_valid_rows_accepted(self):
        result = self._submit(rows=[make_row()])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"], 0)

    def test_accepted_row_written_to_sale_table(self):
        self._submit(rows=[make_row()])
        self.assertEqual(Sale.objects.count(), 1)

    def test_saleimport_created_for_each_row(self):
        self._submit(rows=[make_row()] * 4)
        self.assertEqual(SaleImport.objects.count(), 4)

    def test_accepted_saleimport_has_correct_status(self):
        self._submit(rows=[make_row()])
        self.assertEqual(SaleImport.objects.get().status, SaleImport.STATUS_ACCEPTED)

    def test_token_stamped_on_saleimport(self):
        self._submit()
        self.assertEqual(SaleImport.objects.get().token, self.token)

    def test_last_sale_datetime_updated_on_contract(self):
        self._submit(rows=[make_row()])
        self.contract.refresh_from_db()
        self.assertIsNotNone(self.contract.last_sale_datetime)

    # ── Rejection cases ──

    def test_unknown_external_designation_rejected(self):
        result = self._submit(rows=[make_row(ext="UNKNOWN")])
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["accepted"], 0)

    def test_rejected_row_reason_mentions_product(self):
        result = self._submit(rows=[make_row(ext="UNKNOWN")])
        self.assertIn("UNKNOWN", result["errors"][0]["reason"])

    def test_zero_quantity_rejected(self):
        self.assertEqual(self._submit(rows=[make_row(quantity=0)])["rejected"], 1)

    def test_zero_ppv_rejected(self):
        self.assertEqual(self._submit(rows=[make_row(ppv=0)])["rejected"], 1)

    def test_sale_before_contract_start_rejected(self):
        row = make_row()
        row["sale_datetime"] = self.contract.start_date - timedelta(days=5)
        self.assertEqual(self._submit(rows=[row])["rejected"], 1)

    def test_sale_after_contract_end_rejected(self):
        row = make_row()
        row["sale_datetime"] = self.contract.end_date + timedelta(days=1)
        self.assertEqual(self._submit(rows=[row])["rejected"], 1)

    def test_rejected_row_stays_in_saleimport_only(self):
        self._submit(rows=[make_row(ext="UNKNOWN")])
        self.assertEqual(SaleImport.objects.filter(status="rejected").count(), 1)
        self.assertEqual(Sale.objects.count(), 0)

    def test_last_sale_datetime_not_updated_when_all_rejected(self):
        self._submit(rows=[make_row(ext="UNKNOWN")])
        self.contract.refresh_from_db()
        self.assertIsNone(self.contract.last_sale_datetime)

    # ── Mixed batch ──

    def test_mixed_batch_counts_are_correct(self):
        result = self._submit(rows=[make_row("DOLI1000"), make_row("UNKNOWN")])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"], 1)

    def test_error_list_has_correct_index(self):
        result = self._submit(rows=[make_row("DOLI1000"), make_row("UNKNOWN")])
        self.assertEqual(result["errors"][0]["index"], 1)

    # ── Idempotency (retry) ──

    def test_duplicate_batch_does_not_create_duplicate_sales(self):
        rows = [make_row()]
        self._submit(rows=rows, batch_id="BATCH-RETRY")
        self._submit(rows=rows, batch_id="BATCH-RETRY")
        self.assertEqual(Sale.objects.count(), 1)

    def test_duplicate_batch_creates_two_saleimport_rows(self):
        """SaleImport always records the raw row, even on retry."""
        rows = [make_row()]
        self._submit(rows=rows, batch_id="BATCH-RETRY")
        self._submit(rows=rows, batch_id="BATCH-RETRY")
        self.assertEqual(SaleImport.objects.filter(batch_id="BATCH-RETRY").count(), 2)

    # ── last_sale_datetime takes the max ──

    def test_last_sale_datetime_is_max_of_accepted_rows(self):
        now   = timezone.now()
        early = now - timedelta(hours=5)
        late  = now - timedelta(hours=1)
        rows  = [
            {**make_row(), "sale_datetime": early, "creation_datetime": early},
            {**make_row(), "sale_datetime": late,  "creation_datetime": late},
        ]
        self._submit(rows=rows)
        self.contract.refresh_from_db()
        self.assertEqual(
            self.contract.last_sale_datetime.replace(microsecond=0),
            late.replace(microsecond=0),
        )

    # ── New validation rules (E11, E12) ──

    def test_future_sale_datetime_is_rejected(self):
        row = {**make_row(), "sale_datetime": timezone.now() + timedelta(hours=2),
               "creation_datetime": timezone.now() + timedelta(hours=2)}
        result = self._submit(rows=[row])
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["accepted"], 0)

    def test_creation_datetime_before_sale_datetime_is_rejected(self):
        now = timezone.now()
        row = {**make_row(),
               "sale_datetime":     now - timedelta(hours=1),
               "creation_datetime": now - timedelta(hours=5)}
        result = self._submit(rows=[row])
        self.assertEqual(result["rejected"], 1)

    # ── last_sale_datetime never goes backwards (G8 / I2) ──

    def test_last_sale_datetime_not_overwritten_by_older_batch(self):
        now   = timezone.now()
        late  = now - timedelta(hours=1)
        early = now - timedelta(hours=6)

        self._submit(rows=[{**make_row(), "sale_datetime": late,  "creation_datetime": late}],
                     batch_id="BATCH-001")
        self._submit(rows=[{**make_row(), "sale_datetime": early, "creation_datetime": early}],
                     batch_id="BATCH-002")

        self.contract.refresh_from_db()
        self.assertEqual(
            self.contract.last_sale_datetime.replace(microsecond=0),
            late.replace(microsecond=0),
        )

    # ── Duplicate rows within same batch (H4) ──

    def test_duplicate_rows_in_batch_create_one_sale(self):
        row = make_row()
        result = self._submit(rows=[row, row])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(SaleImport.objects.count(), 2)

    # ── Same sale across two different batches (H5) ──

    def test_same_sale_in_two_batches_creates_one_sale(self):
        row = make_row()
        self._submit(rows=[row], batch_id="BATCH-001")
        self._submit(rows=[row], batch_id="BATCH-002")
        self.assertEqual(Sale.objects.count(), 1)

    # ── Inactive account raises AccountNotFoundError (D3) ──

    def test_raises_account_not_found_for_inactive_account(self):
        inactive_account = make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        with self.assertRaises(AccountNotFoundError):
            self._submit(account_code="PH-INACTIVE")


# ===========================================================================
# confirm_sync()
# ===========================================================================

class ConfirmSyncTests(TestCase):

    def setUp(self):
        self.token    = make_token()
        self.account  = make_account()
        self.product  = make_product()
        self.contract = make_contract(self.account)
        Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )

    def _sync(self, reported_dt=None, batch_id="BATCH-001"):
        return confirm_sync(
            account_code="PH-TEST",
            batch_id=batch_id,
            pharmacy_last_sale_datetime=reported_dt,
        )

    def _submit(self, batch_id="BATCH-001"):
        submit_sales_batch(
            account_code="PH-TEST",
            batch_id=batch_id,
            sales_data=[make_row()],
            token=self.token,
        )

    # ── Return value ──

    def test_returns_dict_with_expected_keys(self):
        for key in ("contract_id", "last_sync_at", "last_sale_datetime", "sync_status", "mismatch"):
            self.assertIn(key, self._sync())

    def test_contract_id_is_correct(self):
        self.assertEqual(self._sync()["contract_id"], self.contract.pk)

    def test_last_sync_at_is_set_on_contract(self):
        self.assertIsNone(self.contract.last_sync_at)
        self._sync()
        self.contract.refresh_from_db()
        self.assertIsNotNone(self.contract.last_sync_at)

    # ── Ok case ──

    def test_sync_ok_when_datetimes_match(self):
        self._submit()
        self.contract.refresh_from_db()
        result = self._sync(reported_dt=self.contract.last_sale_datetime)
        self.assertEqual(result["sync_status"], "ok")
        self.assertFalse(result["mismatch"])

    def test_detail_absent_on_ok(self):
        self._submit()
        self.contract.refresh_from_db()
        result = self._sync(reported_dt=self.contract.last_sale_datetime)
        self.assertNotIn("detail", result)

    def test_sync_ok_when_no_datetime_reported(self):
        self.assertEqual(self._sync(reported_dt=None)["sync_status"], "ok")

    # ── Mismatch case ──

    def test_sync_warning_on_mismatch(self):
        self._submit()
        result = self._sync(reported_dt=timezone.now() + timedelta(hours=99))
        self.assertEqual(result["sync_status"], "warning")
        self.assertTrue(result["mismatch"])

    def test_detail_present_on_mismatch(self):
        self._submit()
        result = self._sync(reported_dt=timezone.now() + timedelta(hours=99))
        self.assertIn("detail", result)

    # ── Pending rows warning ──

    def test_pending_warning_when_pending_rows_exist(self):
        SaleImport.objects.create(
            batch_id="BATCH-001", account_code="PH-TEST",
            external_designation="DOLI1000",
            sale_datetime=timezone.now(), creation_datetime=timezone.now(),
            quantity=1, ppv=10,
            status=SaleImport.STATUS_PENDING, token=self.token,
        )
        result = self._sync(batch_id="BATCH-001")
        self.assertIn("pending_warning", result)
        self.assertEqual(result["sync_status"], "warning")

    def test_no_pending_warning_when_all_rows_processed(self):
        self._submit(batch_id="BATCH-001")
        self.assertNotIn("pending_warning", self._sync(batch_id="BATCH-001"))

    # ── Errors ──

    def test_raises_account_not_found(self):
        with self.assertRaises(AccountNotFoundError):
            confirm_sync("PH-UNKNOWN", "BATCH-001", None)

    def test_raises_account_not_found_for_inactive_account(self):
        make_account(code="PH-INACTIVE", status=STATUS_INACTIVE)
        with self.assertRaises(AccountNotFoundError):
            confirm_sync("PH-INACTIVE", "BATCH-001", None)

    def test_raises_contract_not_found(self):
        account = make_account(code="PH-002")
        make_contract(account, status=STATUS_INACTIVE)
        with self.assertRaises(ContractNotFoundError):
            confirm_sync("PH-002", "BATCH-001", None)

    # ── Sync called twice: last_sync_at updates (J8) ──

    def test_last_sync_at_updates_on_second_call(self):
        self._sync()
        self.contract.refresh_from_db()
        first = self.contract.last_sync_at

        self._sync()
        self.contract.refresh_from_db()
        second = self.contract.last_sync_at

        self.assertGreaterEqual(second, first)

    # ── Sync for batch never submitted (J11) ──

    def test_sync_for_unsubmitted_batch_succeeds(self):
        result = confirm_sync("PH-TEST", "BATCH-NEVER-SENT", None)
        self.assertEqual(result["sync_status"], "ok")
        self.assertNotIn("pending_warning", result)

    # ── Pharmacy reports more than we accepted (J4) ──

    def test_sync_warning_when_pharmacy_reports_more_than_accepted(self):
        self._submit()
        future_dt = timezone.now() + timedelta(hours=2)
        result = self._sync(reported_dt=future_dt)
        self.assertEqual(result["sync_status"], "warning")
        self.assertTrue(result["mismatch"])
