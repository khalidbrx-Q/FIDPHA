"""
control/tests.py
----------------
Test suite for the control panel app.

Covers:
  - Auto-review mechanism (both flags, partial flags, service layer)
  - Sales review views: accept, reject, bulk accept, bulk update
  - System settings view (POST updates SystemConfig)
  - Access control: non-staff redirect, staff-without-perm 403, superuser bypass

How to run:
    python manage.py test control
    python manage.py test control.tests.AutoReviewTests
    python manage.py test control.tests.SalesReviewViewTests
    python manage.py test control.tests.SystemSettingsViewTests
    python manage.py test control.tests.AccessControlTests

Author: FIDPHA Dev Team
Last updated: May 2026
"""

from datetime import timedelta

from django.contrib.auth.models import User, Permission
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from api.models import APIToken
from control.models import SystemConfig
from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import STATUS_ACTIVE, STATUS_INACTIVE
from sales.models import Sale, SaleImport
from sales.services import submit_sales_batch


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_account(code="PH-TEST", auto_review=False, status=STATUS_ACTIVE):
    return Account.objects.create(
        code=code, name="Test Pharmacy",
        city="Casablanca", location="123 Test Street",
        phone="0600000000", email="test@pharmacy.ma",
        pharmacy_portal=True, status=status,
        auto_review_enabled=auto_review,
    )


def make_product(code="PROD-001", ppv="12.50"):
    return Product.objects.create(
        code=code, designation="Doliprane 1000", status=STATUS_ACTIVE, ppv=ppv,
    )


def make_contract(account, status=STATUS_ACTIVE):
    now = timezone.now()
    return Contract.objects.create(
        title="Test Contract",
        designation="Test contract description.",
        start_date=now - timedelta(days=3),
        end_date=now + timedelta(days=30),
        account=account,
        status=status,
    )


def make_token(name="Test Token"):
    return APIToken.objects.create(name=name, is_active=True)


def make_sale_row(ext="DOLI1000", hours_ago=2, quantity=1, ppv=12.50):
    dt = timezone.now() - timedelta(days=1, hours=hours_ago)
    return {
        "external_designation": ext,
        "sale_datetime":        dt,
        "creation_datetime":    dt,
        "quantity":             quantity,
        "ppv":                  ppv,
    }


def make_pending_sale(contract, product, cp):
    """Create a SaleImport + Sale pair in STATUS_PENDING directly."""
    dt = timezone.now() - timedelta(days=1, hours=2)
    si = SaleImport.objects.create(
        batch_id="TEST-BATCH-001",
        account_code=contract.account.code,
        external_designation=cp.external_designation,
        sale_datetime=dt,
        creation_datetime=dt,
        quantity=1,
        ppv=product.ppv,
        status=SaleImport.STATUS_ACCEPTED,
        contract_product=cp,
    )
    return Sale.objects.create(
        sale_import=si,
        contract_product=cp,
        sale_datetime=dt,
        creation_datetime=dt,
        quantity=1,
        ppv=si.ppv,
        product_ppv=product.ppv,
        status=Sale.STATUS_PENDING,
    )


def make_superuser(username="admin"):
    return User.objects.create_user(
        username=username, password="AdminPass123!", is_staff=True, is_superuser=True
    )


def make_staff_user(username="staff", perms=None):
    """Create a staff user, optionally grant a list of 'app.codename' permissions."""
    user = User.objects.create_user(
        username=username, password="StaffPass123!", is_staff=True
    )
    if perms:
        for perm_str in perms:
            app_label, codename = perm_str.split(".")
            perm = Permission.objects.get(
                content_type__app_label=app_label, codename=codename
            )
            user.user_permissions.add(perm)
    return user


# ===========================================================================
# Auto-review mechanism
# ===========================================================================

class AutoReviewTests(TestCase):
    """
    Tests for the auto-review hook inside submit_sales_batch().

    Rule: auto-review fires only when BOTH SystemConfig.auto_review_enabled
    AND Account.auto_review_enabled are True.
    """

    def setUp(self):
        self.token   = make_token()
        self.product = make_product()

    def _setup_account_and_contract(self, global_on, per_account_on):
        SystemConfig.objects.update_or_create(
            pk=1,
            defaults={"auto_review_enabled": global_on},
        )
        account  = make_account(code="PH-AR", auto_review=per_account_on)
        contract = make_contract(account)
        Contract_Product.objects.create(
            contract=contract,
            product=self.product,
            external_designation="DOLI1000",
        )
        return account, contract

    def _submit(self, account_code="PH-AR"):
        return submit_sales_batch(
            account_code=account_code,
            batch_id="BATCH-AR-001",
            sales_data=[make_sale_row()],
            token=self.token,
        )

    # ── Both flags ON ──

    def test_sale_is_auto_accepted_when_both_flags_on(self):
        self._setup_account_and_contract(global_on=True, per_account_on=True)
        self._submit()
        sale = Sale.objects.get()
        self.assertEqual(sale.status, Sale.STATUS_ACCEPTED)

    def test_auto_reviewed_flag_is_true_when_both_flags_on(self):
        self._setup_account_and_contract(global_on=True, per_account_on=True)
        self._submit()
        sale = Sale.objects.get()
        self.assertTrue(sale.auto_reviewed)

    def test_reviewed_by_is_none_on_auto_review(self):
        """Auto-review is a system action — reviewed_by must stay None."""
        self._setup_account_and_contract(global_on=True, per_account_on=True)
        self._submit()
        sale = Sale.objects.get()
        self.assertIsNone(sale.reviewed_by)

    def test_reviewed_at_is_set_on_auto_review(self):
        self._setup_account_and_contract(global_on=True, per_account_on=True)
        self._submit()
        sale = Sale.objects.get()
        self.assertIsNotNone(sale.reviewed_at)

    # ── Global OFF, per-account ON ──

    def test_sale_stays_pending_when_global_off_per_account_on(self):
        self._setup_account_and_contract(global_on=False, per_account_on=True)
        self._submit()
        sale = Sale.objects.get()
        self.assertEqual(sale.status, Sale.STATUS_PENDING)

    def test_auto_reviewed_false_when_global_off(self):
        self._setup_account_and_contract(global_on=False, per_account_on=True)
        self._submit()
        sale = Sale.objects.get()
        self.assertFalse(sale.auto_reviewed)

    # ── Global ON, per-account OFF ──

    def test_sale_stays_pending_when_global_on_per_account_off(self):
        self._setup_account_and_contract(global_on=True, per_account_on=False)
        self._submit()
        sale = Sale.objects.get()
        self.assertEqual(sale.status, Sale.STATUS_PENDING)

    def test_auto_reviewed_false_when_per_account_off(self):
        self._setup_account_and_contract(global_on=True, per_account_on=False)
        self._submit()
        sale = Sale.objects.get()
        self.assertFalse(sale.auto_reviewed)

    # ── Both OFF ──

    def test_sale_stays_pending_when_both_flags_off(self):
        self._setup_account_and_contract(global_on=False, per_account_on=False)
        self._submit()
        sale = Sale.objects.get()
        self.assertEqual(sale.status, Sale.STATUS_PENDING)

    # ── Multiple rows in one batch ──

    def test_all_rows_auto_accepted_when_both_flags_on(self):
        self._setup_account_and_contract(global_on=True, per_account_on=True)
        submit_sales_batch(
            account_code="PH-AR",
            batch_id="BATCH-AR-MULTI",
            sales_data=[make_sale_row(hours_ago=4), make_sale_row(hours_ago=2)],
            token=self.token,
        )
        self.assertEqual(
            Sale.objects.filter(status=Sale.STATUS_ACCEPTED).count(), 2
        )
        self.assertEqual(
            Sale.objects.filter(auto_reviewed=True).count(), 2
        )

    # ── Rejected rows are not auto-reviewed ──

    def test_rejected_row_is_not_auto_reviewed(self):
        """A row rejected at validation stage must not be auto-reviewed."""
        self._setup_account_and_contract(global_on=True, per_account_on=True)
        submit_sales_batch(
            account_code="PH-AR",
            batch_id="BATCH-AR-REJ",
            sales_data=[make_sale_row(ext="UNKNOWN")],
            token=self.token,
        )
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(
            SaleImport.objects.filter(status=SaleImport.STATUS_REJECTED).count(), 1
        )


# ===========================================================================
# Sales review views
# ===========================================================================

class SalesReviewViewTests(TestCase):
    """
    Tests for sale_accept, sale_reject, sales_bulk_accept, sales_bulk_update.
    Uses a superuser to avoid per-permission setup noise.
    """

    def setUp(self):
        self.user    = make_superuser()
        self.client  = Client()
        self.client.force_login(self.user)

        self.account  = make_account()
        self.product  = make_product()
        self.contract = make_contract(self.account)
        self.cp       = Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )
        self.sale = make_pending_sale(self.contract, self.product, self.cp)

    # ── sale_accept ──

    def test_accept_sets_status_accepted(self):
        self.client.post(reverse("control:sale_accept", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_ACCEPTED)

    def test_accept_stamps_reviewed_by(self):
        self.client.post(reverse("control:sale_accept", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.reviewed_by, self.user)

    def test_accept_stamps_reviewed_at(self):
        self.client.post(reverse("control:sale_accept", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertIsNotNone(self.sale.reviewed_at)

    def test_accept_get_request_does_not_change_status(self):
        """GET to accept URL is a no-op — only POST changes data."""
        self.client.get(reverse("control:sale_accept", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_PENDING)

    # ── sale_reject ──

    def test_reject_sets_status_rejected(self):
        self.client.post(reverse("control:sale_reject", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_REJECTED)

    def test_reject_stamps_reviewed_by(self):
        self.client.post(reverse("control:sale_reject", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.reviewed_by, self.user)

    def test_reject_get_request_does_not_change_status(self):
        self.client.get(reverse("control:sale_reject", args=[self.sale.pk]))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_PENDING)

    # ── sales_bulk_accept ──

    def test_bulk_accept_accepts_all_pending_in_batch(self):
        # Create a second pending sale in the same batch
        dt = timezone.now() - timedelta(days=1, hours=3)
        si2 = SaleImport.objects.create(
            batch_id="TEST-BATCH-001",
            account_code=self.account.code,
            external_designation="DOLI1000",
            sale_datetime=dt, creation_datetime=dt,
            quantity=2, ppv=12.50,
            status=SaleImport.STATUS_ACCEPTED,
            contract_product=self.cp,
        )
        sale2 = Sale.objects.create(
            sale_import=si2, contract_product=self.cp,
            sale_datetime=dt, creation_datetime=dt,
            quantity=2, ppv=12.50, product_ppv=12.50,
            status=Sale.STATUS_PENDING,
        )
        self.client.post(reverse("control:sales_bulk_accept"), {
            "contract": self.contract.pk,
            "batch":    "TEST-BATCH-001",
        })
        self.sale.refresh_from_db()
        sale2.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_ACCEPTED)
        self.assertEqual(sale2.status,     Sale.STATUS_ACCEPTED)

    def test_bulk_accept_does_not_touch_already_accepted_sales(self):
        """Bulk accept must only update STATUS_PENDING — not re-touch accepted ones."""
        self.sale.status = Sale.STATUS_ACCEPTED
        self.sale.reviewed_by = self.user
        self.sale.save(update_fields=["status", "reviewed_by"])
        original_reviewed_by = self.sale.reviewed_by

        self.client.post(reverse("control:sales_bulk_accept"), {
            "contract": self.contract.pk,
            "batch":    "TEST-BATCH-001",
        })
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.reviewed_by, original_reviewed_by)

    # ── sales_bulk_update ──

    def test_bulk_update_accept(self):
        response = self.client.post(
            reverse("control:sales_bulk_update"),
            {"pks": str(self.sale.pk), "status": Sale.STATUS_ACCEPTED},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_ACCEPTED)

    def test_bulk_update_reject_with_reason(self):
        response = self.client.post(
            reverse("control:sales_bulk_update"),
            {"pks": str(self.sale.pk), "status": Sale.STATUS_REJECTED, "reason": "Duplicate"},
        )
        self.assertTrue(response.json()["ok"])
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status,           Sale.STATUS_REJECTED)
        self.assertEqual(self.sale.rejection_reason, "Duplicate")

    def test_bulk_update_returns_400_for_invalid_status(self):
        response = self.client.post(
            reverse("control:sales_bulk_update"),
            {"pks": str(self.sale.pk), "status": "invalid"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_bulk_update_returns_400_when_no_pks(self):
        response = self.client.post(
            reverse("control:sales_bulk_update"),
            {"pks": "", "status": Sale.STATUS_ACCEPTED},
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_update_updated_count_in_response(self):
        response = self.client.post(
            reverse("control:sales_bulk_update"),
            {"pks": str(self.sale.pk), "status": Sale.STATUS_ACCEPTED},
        )
        self.assertEqual(response.json()["updated"], 1)

    def test_bulk_update_get_returns_405(self):
        response = self.client.get(reverse("control:sales_bulk_update"))
        self.assertEqual(response.status_code, 405)


# ===========================================================================
# System settings view
# ===========================================================================

class SystemSettingsViewTests(TestCase):
    """Tests for GET/POST /control/settings/system/ (superuser only)."""

    def setUp(self):
        self.user   = make_superuser()
        self.client = Client()
        self.client.force_login(self.user)

    def test_get_returns_200(self):
        response = self.client.get(reverse("control:system_settings"))
        self.assertEqual(response.status_code, 200)

    def test_post_enables_auto_review(self):
        self.client.post(
            reverse("control:system_settings"),
            {"auto_review_enabled": "1"},
        )
        self.assertTrue(SystemConfig.get().auto_review_enabled)

    def test_post_disables_auto_review(self):
        SystemConfig.objects.update_or_create(pk=1, defaults={"auto_review_enabled": True})
        self.client.post(
            reverse("control:system_settings"),
            {},  # auto_review_enabled not sent → treated as off
        )
        self.assertFalse(SystemConfig.get().auto_review_enabled)

    def test_post_stamps_updated_by(self):
        self.client.post(
            reverse("control:system_settings"),
            {"auto_review_enabled": "1"},
        )
        config = SystemConfig.get()
        self.assertEqual(config.auto_review_updated_by, self.user)

    def test_post_redirects_back_to_settings(self):
        response = self.client.post(
            reverse("control:system_settings"),
            {"auto_review_enabled": "1"},
        )
        self.assertRedirects(response, reverse("control:system_settings"))


# ===========================================================================
# Token views
# ===========================================================================

class TokenViewTests(TestCase):
    """Tests for tokens_revoke and tokens_reactivate."""

    def setUp(self):
        self.user   = make_superuser()
        self.client = Client()
        self.client.force_login(self.user)
        self.token  = make_token(name="Pharmacy Token")

    def test_revoke_sets_is_active_false(self):
        self.client.post(reverse("control:tokens_revoke", args=[self.token.pk]))
        self.token.refresh_from_db()
        self.assertFalse(self.token.is_active)

    def test_revoke_get_does_not_change_token(self):
        self.client.get(reverse("control:tokens_revoke", args=[self.token.pk]))
        self.token.refresh_from_db()
        self.assertTrue(self.token.is_active)

    def test_reactivate_sets_is_active_true(self):
        self.token.is_active = False
        self.token.save(update_fields=["is_active"])
        self.client.post(reverse("control:tokens_reactivate", args=[self.token.pk]))
        self.token.refresh_from_db()
        self.assertTrue(self.token.is_active)

    def test_revoke_nonexistent_token_returns_404(self):
        response = self.client.post(reverse("control:tokens_revoke", args=[99999]))
        self.assertEqual(response.status_code, 404)


# ===========================================================================
# Access control
# ===========================================================================

class AccessControlTests(TestCase):
    """
    Tests that access rules are enforced:
    - Non-staff → redirect to portal login
    - Staff without perm → 403
    - Superuser → access granted (bypasses perm check)
    """

    def setUp(self):
        self.account  = make_account()
        self.product  = make_product()
        self.contract = make_contract(self.account)
        self.cp       = Contract_Product.objects.create(
            contract=self.contract, product=self.product,
            external_designation="DOLI1000",
        )
        self.sale = make_pending_sale(self.contract, self.product, self.cp)

        self.superuser = make_superuser("superuser")
        self.staff_no_perm = make_staff_user("staff_noperm")
        self.regular_user  = User.objects.create_user(
            username="portal_user", password="pass", is_staff=False
        )

    # ── Non-staff redirected ──

    def test_non_staff_redirected_from_sales_list(self):
        c = Client()
        c.force_login(self.regular_user)
        response = c.get(reverse("control:sales_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/portal/login/", response["Location"])

    def test_non_staff_redirected_from_system_settings(self):
        c = Client()
        c.force_login(self.regular_user)
        response = c.get(reverse("control:system_settings"))
        self.assertEqual(response.status_code, 302)

    # ── Staff without perm gets 403 ──

    def test_staff_without_perm_gets_403_on_sale_accept(self):
        c = Client()
        c.force_login(self.staff_no_perm)
        response = c.post(reverse("control:sale_accept", args=[self.sale.pk]))
        self.assertEqual(response.status_code, 403)

    def test_staff_without_perm_gets_403_on_sale_reject(self):
        c = Client()
        c.force_login(self.staff_no_perm)
        response = c.post(reverse("control:sale_reject", args=[self.sale.pk]))
        self.assertEqual(response.status_code, 403)

    def test_staff_without_perm_gets_403_on_bulk_accept(self):
        c = Client()
        c.force_login(self.staff_no_perm)
        response = c.post(reverse("control:sales_bulk_accept"), {
            "contract": self.contract.pk,
            "batch":    "TEST-BATCH-001",
        })
        self.assertEqual(response.status_code, 403)

    def test_staff_without_perm_gets_403_on_system_settings(self):
        c = Client()
        c.force_login(self.staff_no_perm)
        response = c.get(reverse("control:system_settings"))
        self.assertEqual(response.status_code, 403)

    # ── Superuser bypasses perm check ──

    def test_superuser_can_access_sale_accept(self):
        c = Client()
        c.force_login(self.superuser)
        response = c.post(reverse("control:sale_accept", args=[self.sale.pk]))
        # Should redirect, not 403
        self.assertNotEqual(response.status_code, 403)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_ACCEPTED)

    def test_superuser_can_access_system_settings(self):
        c = Client()
        c.force_login(self.superuser)
        response = c.get(reverse("control:system_settings"))
        self.assertEqual(response.status_code, 200)

    # ── Staff with correct perm gets through ──

    def test_staff_with_change_sale_perm_can_accept(self):
        user = make_staff_user("staff_with_perm", perms=["sales.change_sale"])
        c = Client()
        c.force_login(user)
        response = c.post(reverse("control:sale_accept", args=[self.sale.pk]))
        self.assertNotEqual(response.status_code, 403)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_ACCEPTED)
