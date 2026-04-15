"""
fidpha/tests.py
---------------
Test suite for the fidpha app.

Tests are organized into classes by the component being tested:

  Services  — business logic functions in fidpha/services.py
  AdminAPI  — AJAX endpoint functions in fidpha/admin_api.py

Each test class has a setUp() method that creates the minimum data
needed for that class's tests. Tests never share state — Django wipes
the test database between every individual test method automatically.

How to run:
    python manage.py test fidpha          ← run only this app
    python manage.py test                 ← run all apps
    python manage.py test fidpha.tests.GetAccountServiceTests  ← one class

Author: FIDPHA Dev Team
Last updated: April 2026
"""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone

from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    AccountNotFoundError,
    ContractNotFoundError,
    ProductNotFoundError,
    ProductAlreadyLinkedError,
    get_account,
    get_active_contract,
    get_contract_products,
    get_available_products_for_contract,
    get_active_contracts_for_product,
    link_product_to_contract,
)


# ---------------------------------------------------------------------------
# Shared factory helpers
# Using helper functions (not fixtures or factories) keeps setup readable
# and makes it obvious what data each test actually depends on.
# ---------------------------------------------------------------------------

def make_account(
    code: str = "PH-TEST",
    name: str = "Test Pharmacy",
    status: str = STATUS_ACTIVE,
    pharmacy_portal: bool = True,
) -> Account:
    """Create and return a minimal valid Account instance."""
    return Account.objects.create(
        code=code,
        name=name,
        city="Casablanca",
        location="123 Test Street, Casablanca",
        phone="0600000000",
        email="test@pharmacy.ma",
        pharmacy_portal=pharmacy_portal,
        status=status,
    )


def make_product(
    code: str = "PROD-001",
    designation: str = "Doliprane 1000",
    status: str = STATUS_ACTIVE,
) -> Product:
    """Create and return a minimal valid Product instance."""
    return Product.objects.create(
        code=code,
        designation=designation,
        status=status,
    )


def make_contract(
    account: Account,
    status: str = STATUS_ACTIVE,
    days_ahead: int = 30,
) -> Contract:
    """
    Create and return a minimal valid Contract instance.

    start_date is set to now, end_date is set to now + days_ahead.
    Both are timezone-aware to match USE_TZ = True in settings.
    """
    now = timezone.now()
    return Contract.objects.create(
        title="Test Contract",
        designation="Test contract description.",
        start_date=now,
        end_date=now + timedelta(days=days_ahead),
        account=account,
        status=status,
    )


def link_product(
    contract: Contract,
    product: Product,
    external_designation: str = "EXT-DESIGNATION",
) -> Contract_Product:
    """Create and return a Contract_Product linking record."""
    return Contract_Product.objects.create(
        contract=contract,
        product=product,
        external_designation=external_designation,
    )


# ===========================================================================
# SERVICE TESTS — fidpha/services.py
# ===========================================================================


class GetAccountServiceTests(TestCase):
    """
    Tests for get_account(account_code).

    This service is the single entry point for resolving an Account by
    its unique code. Every other account-related operation builds on it.
    """

    def setUp(self):
        self.account = make_account(code="PH-001")

    def test_returns_correct_account_for_valid_code(self):
        """Happy path: a known code returns the matching Account instance."""
        result = get_account("PH-001")
        self.assertEqual(result.pk, self.account.pk)

    def test_returned_account_has_correct_name(self):
        """Sanity check: the returned object carries the right data."""
        result = get_account("PH-001")
        self.assertEqual(result.name, self.account.name)

    def test_raises_account_not_found_for_unknown_code(self):
        """An unknown code must raise AccountNotFoundError, not DoesNotExist."""
        with self.assertRaises(AccountNotFoundError):
            get_account("PH-DOES-NOT-EXIST")

    def test_raises_account_not_found_for_empty_string(self):
        """An empty string must raise AccountNotFoundError, not crash."""
        with self.assertRaises(AccountNotFoundError):
            get_account("")

    def test_code_lookup_is_case_sensitive(self):
        """
        Account codes are stored exactly as created.
        Looking up with wrong casing must not match.
        """
        with self.assertRaises(AccountNotFoundError):
            get_account("ph-001")


# ---------------------------------------------------------------------------


class GetActiveContractServiceTests(TestCase):
    """
    Tests for get_active_contract(account_code).

    Builds on get_account() and adds the active contract lookup.
    Business Rule 1: only one active contract per account is allowed.
    """

    def setUp(self):
        self.account = make_account(code="PH-001")
        self.active_contract = make_contract(self.account, status=STATUS_ACTIVE)

    def test_returns_the_active_contract(self):
        """Happy path: account with an active contract returns that contract."""
        result = get_active_contract("PH-001")
        self.assertEqual(result.pk, self.active_contract.pk)

    def test_raises_account_not_found_for_unknown_account(self):
        """An unknown account code must propagate as AccountNotFoundError."""
        with self.assertRaises(AccountNotFoundError):
            get_active_contract("PH-UNKNOWN")

    def test_raises_contract_not_found_when_account_has_no_contracts(self):
        """An account with zero contracts must raise ContractNotFoundError."""
        empty_account = make_account(code="PH-002")

        with self.assertRaises(ContractNotFoundError):
            get_active_contract("PH-002")

    def test_raises_contract_not_found_when_only_inactive_contract_exists(self):
        """An account whose only contract is inactive must raise ContractNotFoundError."""
        account = make_account(code="PH-003")
        make_contract(account, status=STATUS_INACTIVE)

        with self.assertRaises(ContractNotFoundError):
            get_active_contract("PH-003")

    def test_does_not_return_inactive_contract_when_no_active_exists(self):
        """
        Inactive contracts must never be returned as the active one.
        This guards against a regression where status filtering is removed.
        """
        account = make_account(code="PH-004")
        inactive_contract = make_contract(account, status=STATUS_INACTIVE)

        with self.assertRaises(ContractNotFoundError):
            result = get_active_contract("PH-004")


# ---------------------------------------------------------------------------


class GetContractProductsServiceTests(TestCase):
    """
    Tests for get_contract_products(contract).

    This service builds the product list included in the API response.
    Each entry maps the product's internal code to its external designation.
    """

    def setUp(self):
        self.account = make_account()
        self.contract = make_contract(self.account)
        self.product = make_product(code="PROD-001", designation="Doliprane 1000")
        link_product(self.contract, self.product, external_designation="DOLI1000")

    def test_returns_list_with_correct_length(self):
        """A contract with one product must return a list of length 1."""
        result = get_contract_products(self.contract)
        self.assertEqual(len(result), 1)

    def test_product_entry_contains_required_keys(self):
        """Each product dict must contain all three required keys."""
        result = get_contract_products(self.contract)
        entry = result[0]

        self.assertIn("product_id", entry)
        self.assertIn("internal_code", entry)
        self.assertIn("external_designation", entry)

    def test_product_entry_values_are_correct(self):
        """Product entry values must match the linked product and junction record."""
        result = get_contract_products(self.contract)
        entry = result[0]

        self.assertEqual(entry["product_id"], self.product.pk)
        self.assertEqual(entry["internal_code"], "PROD-001")
        self.assertEqual(entry["external_designation"], "DOLI1000")

    def test_returns_empty_list_when_contract_has_no_products(self):
        """A contract with no linked products must return [], not raise an error."""
        empty_contract = make_contract(self.account)
        result = get_contract_products(empty_contract)
        self.assertEqual(result, [])

    def test_returns_all_linked_products(self):
        """All products linked to the contract must appear in the result."""
        product_2 = make_product(code="PROD-002", designation="Amoxicilline 500")
        link_product(self.contract, product_2, external_designation="AMOX500")

        result = get_contract_products(self.contract)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------


class GetAvailableProductsServiceTests(TestCase):
    """
    Tests for get_available_products_for_contract(contract_id).

    Used by the admin "Add Product" modal. Must return only active products
    not already linked to the contract, ordered alphabetically.
    """

    def setUp(self):
        self.account = make_account()
        self.contract = make_contract(self.account)

        # This product IS linked — must not appear in results
        self.linked_product = make_product(
            code="PROD-001",
            designation="Linked Product",
        )
        link_product(self.contract, self.linked_product)

        # This product is NOT linked — must appear in results
        self.available_product = make_product(
            code="PROD-002",
            designation="Available Product",
        )

    def test_includes_unlinked_active_products(self):
        """Active products not yet linked to the contract must be returned."""
        result = get_available_products_for_contract(self.contract.pk)
        result_ids = list(result.values_list("pk", flat=True))

        self.assertIn(self.available_product.pk, result_ids)

    def test_excludes_already_linked_products(self):
        """Products already linked to the contract must not appear."""
        result = get_available_products_for_contract(self.contract.pk)
        result_ids = list(result.values_list("pk", flat=True))

        self.assertNotIn(self.linked_product.pk, result_ids)

    def test_excludes_inactive_products(self):
        """Inactive products must never appear, even if not linked."""
        inactive_product = make_product(
            code="PROD-003",
            designation="Inactive Product",
            status=STATUS_INACTIVE,
        )
        result = get_available_products_for_contract(self.contract.pk)
        result_ids = list(result.values_list("pk", flat=True))

        self.assertNotIn(inactive_product.pk, result_ids)

    def test_results_are_ordered_alphabetically_by_designation(self):
        """Products must be returned in A→Z order by designation."""
        make_product(code="PROD-004", designation="Zinc 50mg")
        make_product(code="PROD-005", designation="Aspirin 500mg")

        result = list(get_available_products_for_contract(self.contract.pk))
        designations = [p.designation for p in result]

        self.assertEqual(designations, sorted(designations))

    def test_raises_does_not_exist_for_unknown_contract(self):
        """A non-existent contract ID must raise Contract.DoesNotExist."""
        with self.assertRaises(Contract.DoesNotExist):
            get_available_products_for_contract(999999)


# ---------------------------------------------------------------------------


class GetActiveContractsForProductServiceTests(TestCase):
    """
    Tests for get_active_contracts_for_product(product).

    Used to enforce Business Rule 2: a product cannot be deactivated if
    it is referenced by at least one active contract.
    """

    def setUp(self):
        self.account = make_account()
        self.product = make_product()
        self.active_contract = make_contract(self.account, status=STATUS_ACTIVE)
        link_product(self.active_contract, self.product)

    def test_returns_active_contracts_containing_the_product(self):
        """Must return all active contracts that reference the given product."""
        result = get_active_contracts_for_product(self.product)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().pk, self.active_contract.pk)

    def test_does_not_return_inactive_contracts(self):
        """Inactive contracts referencing the product must be excluded."""
        account_2 = make_account(code="PH-002")
        inactive_contract = make_contract(account_2, status=STATUS_INACTIVE)
        link_product(inactive_contract, self.product)

        result = get_active_contracts_for_product(self.product)

        # Only the one active contract from setUp must be returned
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().pk, self.active_contract.pk)

    def test_returns_empty_queryset_when_product_not_in_any_contract(self):
        """A product not linked to any contract must return an empty queryset."""
        unlinked_product = make_product(
            code="PROD-999",
            designation="Unlinked Product",
        )
        result = get_active_contracts_for_product(unlinked_product)
        self.assertEqual(result.count(), 0)

    def test_returns_multiple_active_contracts_when_applicable(self):
        """If a product is in multiple active contracts, all must be returned."""
        account_2 = make_account(code="PH-002")
        second_active_contract = make_contract(account_2, status=STATUS_ACTIVE)
        link_product(second_active_contract, self.product)

        result = get_active_contracts_for_product(self.product)
        self.assertEqual(result.count(), 2)


# ---------------------------------------------------------------------------


class LinkProductToContractServiceTests(TestCase):
    """
    Tests for link_product_to_contract(contract_id, product_id, external_designation).

    This is the service that creates Contract_Product records. It validates
    that the product is active and not already linked before creating the record.
    """

    def setUp(self):
        self.account = make_account()
        self.contract = make_contract(self.account)
        self.product = make_product()

    def test_creates_and_returns_contract_product_record(self):
        """Happy path: valid inputs create and return a Contract_Product."""
        result = link_product_to_contract(
            contract_id=self.contract.pk,
            product_id=self.product.pk,
            external_designation="EXT-DOLI",
        )

        self.assertIsInstance(result, Contract_Product)
        self.assertEqual(result.contract.pk, self.contract.pk)
        self.assertEqual(result.product.pk, self.product.pk)
        self.assertEqual(result.external_designation, "EXT-DOLI")

    def test_record_is_persisted_in_the_database(self):
        """The created record must be queryable from the database."""
        link_product_to_contract(
            contract_id=self.contract.pk,
            product_id=self.product.pk,
            external_designation="EXT-DOLI",
        )

        self.assertTrue(
            Contract_Product.objects.filter(
                contract=self.contract,
                product=self.product,
            ).exists()
        )

    def test_raises_does_not_exist_for_unknown_contract(self):
        """A non-existent contract ID must raise Contract.DoesNotExist."""
        with self.assertRaises(Contract.DoesNotExist):
            link_product_to_contract(
                contract_id=999999,
                product_id=self.product.pk,
                external_designation="EXT-DOLI",
            )

    def test_raises_product_not_found_for_unknown_product(self):
        """A non-existent product ID must raise ProductNotFoundError."""
        with self.assertRaises(ProductNotFoundError):
            link_product_to_contract(
                contract_id=self.contract.pk,
                product_id=999999,
                external_designation="EXT-DOLI",
            )

    def test_raises_product_not_found_for_inactive_product(self):
        """
        An inactive product must raise ProductNotFoundError.
        Inactive products cannot be added to contracts (Business Rule 2 inverse).
        """
        inactive_product = make_product(
            code="PROD-OFF",
            designation="Inactive Product",
            status=STATUS_INACTIVE,
        )
        with self.assertRaises(ProductNotFoundError):
            link_product_to_contract(
                contract_id=self.contract.pk,
                product_id=inactive_product.pk,
                external_designation="EXT-OFF",
            )

    def test_raises_already_linked_error_on_duplicate(self):
        """
        Linking the same product to the same contract twice must raise
        ProductAlreadyLinkedError before the DB unique constraint is hit.
        """
        # First link — must succeed
        link_product_to_contract(
            contract_id=self.contract.pk,
            product_id=self.product.pk,
            external_designation="EXT-DOLI",
        )

        # Second link — must be blocked with a meaningful error
        with self.assertRaises(ProductAlreadyLinkedError):
            link_product_to_contract(
                contract_id=self.contract.pk,
                product_id=self.product.pk,
                external_designation="EXT-DOLI-2",
            )

    def test_same_product_can_be_linked_to_different_contracts(self):
        """
        A product can be in multiple contracts as long as it is not
        linked twice to the same contract.
        """
        account_2 = make_account(code="PH-002")
        second_contract = make_contract(account_2)

        # Link to first contract
        link_product_to_contract(
            contract_id=self.contract.pk,
            product_id=self.product.pk,
            external_designation="EXT-A",
        )

        # Link same product to second contract — must succeed
        result = link_product_to_contract(
            contract_id=second_contract.pk,
            product_id=self.product.pk,
            external_designation="EXT-B",
        )
        self.assertIsInstance(result, Contract_Product)


# ===========================================================================
# ADMIN API TESTS — fidpha/admin_api.py
# ===========================================================================


class AdminApiTestBase(TestCase):
    """
    Base class for all admin API test classes.

    Provides:
    - A staff user (self.staff_client): has access to admin endpoints
    - A non-staff user (self.regular_client): must be refused with 403
    - A shared account, contract, and product for convenience
    """

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="admin_user",
            password="AdminPass123!",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="pharmacy_user",
            password="UserPass123!",
            is_staff=False,
        )

        # Pre-authenticated clients — avoids repeating login in every test
        self.staff_client = Client()
        self.staff_client.force_login(self.staff_user)

        self.regular_client = Client()
        self.regular_client.force_login(self.regular_user)

        # Shared test data
        self.account = make_account()
        self.contract = make_contract(self.account)
        self.product = make_product()


# ---------------------------------------------------------------------------


class AvailableProductsApiTests(AdminApiTestBase):
    """Tests for GET /api/contract/<id>/available-products/"""

    def _get(self, contract_id: int, client=None) -> object:
        """Helper to GET the available products endpoint."""
        client = client or self.staff_client
        return client.get(f"/api/contract/{contract_id}/available-products/")

    def test_returns_200_for_staff_user(self):
        """Staff users must receive a 200 response."""
        response = self._get(self.contract.pk)
        self.assertEqual(response.status_code, 200)

    def test_response_contains_products_key(self):
        """Response body must contain a 'products' list."""
        response = self._get(self.contract.pk)
        data = response.json()
        self.assertIn("products", data)

    def test_returns_unlinked_active_products(self):
        """The unlinked active product must appear in the response."""
        response = self._get(self.contract.pk)
        data = response.json()
        result_ids = [p["id"] for p in data["products"]]

        self.assertIn(self.product.pk, result_ids)

    def test_excludes_already_linked_products(self):
        """Products already linked to the contract must not appear."""
        link_product(self.contract, self.product)

        response = self._get(self.contract.pk)
        data = response.json()
        result_ids = [p["id"] for p in data["products"]]

        self.assertNotIn(self.product.pk, result_ids)

    def test_excludes_inactive_products(self):
        """Inactive products must not appear even if unlinked."""
        inactive = make_product(
            code="PROD-OFF",
            designation="Inactive",
            status=STATUS_INACTIVE,
        )
        response = self._get(self.contract.pk)
        data = response.json()
        result_ids = [p["id"] for p in data["products"]]

        self.assertNotIn(inactive.pk, result_ids)

    def test_each_product_entry_has_required_fields(self):
        """Each product in the response must have id, code, and designation."""
        response = self._get(self.contract.pk)
        data = response.json()

        for product_entry in data["products"]:
            self.assertIn("id", product_entry)
            self.assertIn("code", product_entry)
            self.assertIn("designation", product_entry)

    def test_returns_403_for_non_staff_user(self):
        """Non-staff users must be refused with 403."""
        response = self._get(self.contract.pk, client=self.regular_client)
        self.assertEqual(response.status_code, 403)

    def test_returns_404_for_unknown_contract(self):
        """A non-existent contract ID must return 404."""
        response = self._get(999999)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------


class AddContractProductApiTests(AdminApiTestBase):
    """Tests for POST /api/contract/<id>/add-product/"""

    def _post(self, contract_id: int, body: dict, client=None) -> object:
        """Helper to POST JSON to the add-product endpoint."""
        client = client or self.staff_client
        return client.post(
            f"/api/contract/{contract_id}/add-product/",
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_links_product_and_returns_200(self):
        """Happy path: valid data creates the link and returns 200."""
        response = self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DOLI",
        })
        self.assertEqual(response.status_code, 200)

    def test_response_body_indicates_success(self):
        """Success response must contain {"success": true}."""
        response = self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DOLI",
        })
        self.assertTrue(response.json()["success"])

    def test_contract_product_record_is_created_in_database(self):
        """The link must actually be persisted in the database."""
        self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DOLI",
        })

        self.assertTrue(
            Contract_Product.objects.filter(
                contract=self.contract,
                product=self.product,
            ).exists()
        )

    def test_external_designation_is_stored_correctly(self):
        """The external_designation value must be saved as provided."""
        self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "MY-CUSTOM-NAME",
        })

        record = Contract_Product.objects.get(
            contract=self.contract,
            product=self.product,
        )
        self.assertEqual(record.external_designation, "MY-CUSTOM-NAME")

    def test_returns_403_for_non_staff_user(self):
        """Non-staff users must be refused with 403."""
        response = self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DOLI",
        }, client=self.regular_client)
        self.assertEqual(response.status_code, 403)

    def test_returns_405_for_get_request(self):
        """Only POST is accepted — a GET must return 405."""
        response = self.staff_client.get(
            f"/api/contract/{self.contract.pk}/add-product/"
        )
        self.assertEqual(response.status_code, 405)

    def test_returns_400_when_product_id_is_missing(self):
        """A request without product_id must return 400."""
        response = self._post(self.contract.pk, {
            "external_designation": "EXT-DOLI",
        })
        self.assertEqual(response.status_code, 400)

    def test_returns_400_when_external_designation_is_missing(self):
        """A request without external_designation must return 400."""
        response = self._post(self.contract.pk, {
            "product_id": self.product.pk,
        })
        self.assertEqual(response.status_code, 400)

    def test_returns_400_when_external_designation_is_blank(self):
        """A blank external_designation (whitespace only) must return 400."""
        response = self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "   ",
        })
        self.assertEqual(response.status_code, 400)

    def test_returns_404_for_unknown_contract(self):
        """A non-existent contract ID must return 404."""
        response = self._post(999999, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DOLI",
        })
        self.assertEqual(response.status_code, 404)

    def test_returns_404_for_inactive_product(self):
        """An inactive product must not be linkable — must return 404."""
        inactive = make_product(
            code="PROD-OFF",
            designation="Inactive",
            status=STATUS_INACTIVE,
        )
        response = self._post(self.contract.pk, {
            "product_id": inactive.pk,
            "external_designation": "EXT-OFF",
        })
        self.assertEqual(response.status_code, 404)

    def test_returns_400_for_already_linked_product(self):
        """Linking the same product twice to the same contract must return 400."""
        # First link
        link_product(self.contract, self.product)

        # Second link attempt
        response = self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DUPLICATE",
        })
        self.assertEqual(response.status_code, 400)

    def test_duplicate_link_does_not_create_extra_record(self):
        """A blocked duplicate attempt must not create a second DB record."""
        link_product(self.contract, self.product)
        self._post(self.contract.pk, {
            "product_id": self.product.pk,
            "external_designation": "EXT-DUPLICATE",
        })

        count = Contract_Product.objects.filter(
            contract=self.contract,
            product=self.product,
        ).count()
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------


class ProductToggleApiTests(AdminApiTestBase):
    """Tests for GET /api/product/<id>/toggle/?status=<status>"""

    def _toggle(self, product_id: int, new_status: str, client=None) -> object:
        """Helper to call the product toggle endpoint."""
        client = client or self.staff_client
        return client.get(
            f"/api/product/{product_id}/toggle/",
            {"status": new_status},
        )

    def test_activates_an_inactive_product(self):
        """An inactive product with no contract blocking can be activated."""
        inactive = make_product(
            code="PROD-OFF",
            designation="Inactive Product",
            status=STATUS_INACTIVE,
        )
        response = self._toggle(inactive.pk, STATUS_ACTIVE)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["blocked"])
        self.assertEqual(data["new_status"], STATUS_ACTIVE)

    def test_activation_is_persisted_in_database(self):
        """The activated status must be saved to the database."""
        inactive = make_product(
            code="PROD-OFF",
            designation="Inactive Product",
            status=STATUS_INACTIVE,
        )
        self._toggle(inactive.pk, STATUS_ACTIVE)

        inactive.refresh_from_db()
        self.assertEqual(inactive.status, STATUS_ACTIVE)

    def test_deactivates_a_product_not_in_any_active_contract(self):
        """A product not in any active contract can be deactivated freely."""
        response = self._toggle(self.product.pk, STATUS_INACTIVE)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["blocked"])
        self.assertEqual(data["new_status"], STATUS_INACTIVE)

    def test_deactivation_is_persisted_in_database(self):
        """The deactivated status must be saved to the database."""
        self._toggle(self.product.pk, STATUS_INACTIVE)

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, STATUS_INACTIVE)

    def test_blocks_deactivation_when_product_is_in_active_contract(self):
        """
        Deactivating a product linked to an active contract must be blocked.
        This enforces Business Rule 2.
        """
        link_product(self.contract, self.product)

        response = self._toggle(self.product.pk, STATUS_INACTIVE)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["blocked"])

    def test_blocked_response_contains_offending_contract(self):
        """Blocked response must list the contracts preventing deactivation."""
        link_product(self.contract, self.product)

        response = self._toggle(self.product.pk, STATUS_INACTIVE)
        data = response.json()

        self.assertEqual(len(data["contracts"]), 1)
        self.assertEqual(data["contracts"][0]["id"], self.contract.pk)

    def test_blocked_response_contract_entry_has_required_fields(self):
        """Each contract entry in a blocked response must have all expected fields."""
        link_product(self.contract, self.product)

        response = self._toggle(self.product.pk, STATUS_INACTIVE)
        contract_entry = response.json()["contracts"][0]

        self.assertIn("id", contract_entry)
        self.assertIn("title", contract_entry)
        self.assertIn("account", contract_entry)
        self.assertIn("start_date", contract_entry)
        self.assertIn("end_date", contract_entry)
        self.assertIn("url", contract_entry)

    def test_product_status_unchanged_when_deactivation_is_blocked(self):
        """
        When deactivation is blocked, the product's status must remain active.
        The toggle must never be partially applied.
        """
        link_product(self.contract, self.product)
        self._toggle(self.product.pk, STATUS_INACTIVE)

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, STATUS_ACTIVE)

    def test_blocked_response_includes_product_designation(self):
        """Blocked response must name the product so the admin knows what was blocked."""
        link_product(self.contract, self.product)

        response = self._toggle(self.product.pk, STATUS_INACTIVE)
        data = response.json()

        self.assertEqual(data["product"], self.product.designation)

    def test_returns_403_for_non_staff_user(self):
        """Non-staff users must be refused with 403."""
        response = self._toggle(self.product.pk, STATUS_INACTIVE, client=self.regular_client)
        self.assertEqual(response.status_code, 403)

    def test_returns_404_for_unknown_product(self):
        """A non-existent product ID must return 404."""
        response = self._toggle(999999, STATUS_INACTIVE)
        self.assertEqual(response.status_code, 404)
