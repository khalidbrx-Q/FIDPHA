"""
api/tests.py
------------
Test suite for the public REST API (api app).

Tests the ActiveContractView endpoint via the DRF test client,
covering:
  - Authentication (no token, invalid token, revoked token)
  - Parameter validation (missing account_code)
  - Business logic errors (unknown account, no active contract)
  - Success response shape and data correctness
  - Token tracking (usage_count, last_used_at)

How to run:
    python manage.py test api          ← run only this app
    python manage.py test              ← run all apps
    python manage.py test api.tests.ActiveContractViewTests  ← one class

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import APIToken
from fidpha.models import Account, Contract, Contract_Product, Product
from fidpha.services import STATUS_ACTIVE, STATUS_INACTIVE


# ---------------------------------------------------------------------------
# Shared factory helpers
# Identical pattern to fidpha/tests.py — small, explicit, readable.
# ---------------------------------------------------------------------------

def make_account(
    code: str = "PH-TEST",
    name: str = "Test Pharmacy",
    status: str = STATUS_ACTIVE,
) -> Account:
    """Create and return a minimal valid Account instance."""
    return Account.objects.create(
        code=code,
        name=name,
        city="Casablanca",
        location="123 Test Street, Casablanca",
        phone="0600000000",
        email="test@pharmacy.ma",
        pharmacy_portal=True,
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
    """Create and return a minimal valid Contract instance."""
    now = timezone.now()
    return Contract.objects.create(
        title="Test Contract",
        designation="Test contract description.",
        start_date=now,
        end_date=now + timedelta(days=days_ahead),
        account=account,
        status=status,
    )


def make_api_token(name: str = "Test Token", is_active: bool = True) -> APIToken:
    """Create and return an APIToken instance (token is auto-generated)."""
    return APIToken.objects.create(name=name, is_active=is_active)


# ===========================================================================
# API VIEW TESTS — api/views.py
# ===========================================================================


class ActiveContractViewTests(TestCase):
    """
    Tests for GET /api/v1/contract/active/

    This is the only public endpoint in the FIDPHA API. External pharmacy
    software calls it to retrieve the active contract for a given account.

    Authentication flow:
      - No header            → authenticate() returns None → HasAPIToken
                               sees request.auth=None → NotAuthenticated (401)
      - Bad format/value     → authenticate() raises AuthenticationFailed (401)
      - Valid token          → authenticate() returns (None, token) → allowed
    """

    API_URL = "/api/v1/contract/active/"

    def setUp(self):
        # A valid, active token for authenticated requests
        self.token = make_api_token(name="Integration Token")

        # Unauthenticated client — used for auth failure tests
        self.anon_client = APIClient()

        # Authenticated client — used for all other tests
        self.auth_client = APIClient()
        self.auth_client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.token.token}"
        )

        # Standard test data: account → contract → product → link
        self.account = make_account(code="PH-001", name="Pharmacie Saada")
        self.product = make_product(code="PROD-001", designation="Doliprane 1000")
        self.contract = make_contract(self.account, status=STATUS_ACTIVE)
        self.contract_product = Contract_Product.objects.create(
            contract=self.contract,
            product=self.product,
            external_designation="DOLI1000",
        )

    # -----------------------------------------------------------------------
    # Authentication tests
    # -----------------------------------------------------------------------

    def test_returns_401_with_no_authorization_header(self):
        """Requests with no Authorization header must be rejected with 401."""
        response = self.anon_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        self.assertEqual(response.status_code, 401)

    def test_returns_401_with_completely_invalid_token(self):
        """A token value that doesn't exist in the DB must return 401."""
        bad_client = APIClient()
        bad_client.credentials(
            HTTP_AUTHORIZATION="Token thisisabsolutelynotavalidtoken"
        )
        response = bad_client.get(self.API_URL, {"account_code": "PH-001"})
        self.assertEqual(response.status_code, 401)

    def test_returns_401_with_revoked_token(self):
        """
        A token that exists in the DB but is_active=False must return 401.
        Revoked tokens must never be usable even if the value is correct.
        """
        revoked_token = make_api_token(name="Revoked Token", is_active=False)
        bad_client = APIClient()
        bad_client.credentials(
            HTTP_AUTHORIZATION=f"Token {revoked_token.token}"
        )
        response = bad_client.get(self.API_URL, {"account_code": "PH-001"})
        self.assertEqual(response.status_code, 401)

    def test_returns_401_with_malformed_authorization_header(self):
        """
        A header that doesn't follow 'Token <value>' format must return 401.
        Example: 'Bearer <token>' or just the raw token with no prefix.
        """
        bad_client = APIClient()
        bad_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.token.token}"
        )
        response = bad_client.get(self.API_URL, {"account_code": "PH-001"})
        self.assertEqual(response.status_code, 401)

    def test_auth_error_response_follows_error_envelope(self):
        """
        401 responses must follow the standard error envelope format.
        This ensures external consumers get a consistent error structure.
        """
        response = self.anon_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        data = response.json()

        self.assertEqual(data["status"], "error")
        self.assertIn("timestamp", data)
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "INVALID_TOKEN")
        self.assertIn("message", data["error"])

    # -----------------------------------------------------------------------
    # Parameter validation tests
    # -----------------------------------------------------------------------

    def test_returns_400_when_account_code_param_is_missing(self):
        """A request with no account_code query param must return 400."""
        response = self.auth_client.get(self.API_URL)
        self.assertEqual(response.status_code, 400)

    def test_400_response_has_missing_parameter_error_code(self):
        """400 response must include the MISSING_PARAMETER error code."""
        response = self.auth_client.get(self.API_URL)
        data = response.json()

        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"]["code"], "MISSING_PARAMETER")

    def test_400_response_follows_error_envelope(self):
        """400 response must follow the standard error envelope format."""
        response = self.auth_client.get(self.API_URL)
        data = response.json()

        self.assertEqual(data["status"], "error")
        self.assertIn("timestamp", data)
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertIn("message", data["error"])

    # -----------------------------------------------------------------------
    # Business logic error tests
    # -----------------------------------------------------------------------

    def test_returns_404_for_unknown_account_code(self):
        """An account code that doesn't exist in the DB must return 404."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-INVALID"}
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_unknown_account_has_correct_error_code(self):
        """404 for an unknown account must use the ACCOUNT_NOT_FOUND code."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-INVALID"}
        )
        data = response.json()
        self.assertEqual(data["error"]["code"], "ACCOUNT_NOT_FOUND")

    def test_returns_404_when_account_has_no_active_contract(self):
        """An account with only inactive contracts must return 404."""
        account = make_account(code="PH-002")
        make_contract(account, status=STATUS_INACTIVE)

        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-002"}
        )
        self.assertEqual(response.status_code, 404)

    def test_returns_404_when_account_has_no_contracts_at_all(self):
        """An account with zero contracts must return 404."""
        make_account(code="PH-003")

        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-003"}
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_missing_contract_has_correct_error_code(self):
        """404 for a missing active contract must use CONTRACT_NOT_FOUND code."""
        make_account(code="PH-004")

        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-004"}
        )
        data = response.json()
        self.assertEqual(data["error"]["code"], "CONTRACT_NOT_FOUND")

    def test_all_error_responses_have_timestamp(self):
        """
        Every error response must include a timestamp.
        This helps external consumers log and debug API failures.
        """
        # 400 — missing parameter
        r1 = self.auth_client.get(self.API_URL)
        self.assertIn("timestamp", r1.json())

        # 404 — unknown account
        r2 = self.auth_client.get(self.API_URL, {"account_code": "PH-INVALID"})
        self.assertIn("timestamp", r2.json())

    # -----------------------------------------------------------------------
    # Success response tests
    # -----------------------------------------------------------------------

    def test_returns_200_for_valid_authenticated_request(self):
        """Happy path: valid token + valid account_code must return 200."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        self.assertEqual(response.status_code, 200)

    def test_success_response_has_status_success(self):
        """200 response must have 'status': 'success' in the envelope."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        self.assertEqual(response.json()["status"], "success")

    def test_success_response_has_timestamp(self):
        """200 response must include a timestamp field."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        self.assertIn("timestamp", response.json())

    def test_success_response_has_contract_key(self):
        """200 response must include a 'contract' key at the top level."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        self.assertIn("contract", response.json())

    def test_contract_id_matches_active_contract(self):
        """The contract ID in the response must match the active contract."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        contract_data = response.json()["contract"]
        self.assertEqual(contract_data["id"], self.contract.pk)

    def test_contract_pharmacy_name_is_correct(self):
        """The pharmacy field must contain the account's name."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        contract_data = response.json()["contract"]
        self.assertEqual(contract_data["pharmacy"], "Pharmacie Saada")

    def test_contract_account_code_is_correct(self):
        """The account_code in the response must match the queried code."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        contract_data = response.json()["contract"]
        self.assertEqual(contract_data["account_code"], "PH-001")

    def test_contract_dates_are_formatted_as_yyyy_mm_dd(self):
        """start_date and end_date must be formatted as YYYY-MM-DD strings."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        contract_data = response.json()["contract"]

        # Validate both dates match the expected format (YYYY-MM-DD)
        import re
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(contract_data["start_date"], date_pattern)
        self.assertRegex(contract_data["end_date"], date_pattern)

    def test_contract_includes_products_key(self):
        """The contract object must include a 'products' list."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        contract_data = response.json()["contract"]
        self.assertIn("products", contract_data)

    def test_product_list_has_correct_length(self):
        """The products list must contain exactly the linked products."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        products = response.json()["contract"]["products"]
        self.assertEqual(len(products), 1)

    def test_product_entry_has_all_required_fields(self):
        """Each product entry must have product_id, internal_code, external_designation."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        product_entry = response.json()["contract"]["products"][0]

        self.assertIn("product_id", product_entry)
        self.assertIn("internal_code", product_entry)
        self.assertIn("external_designation", product_entry)

    def test_product_entry_values_are_correct(self):
        """Product entry values must match the product and junction record."""
        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        product_entry = response.json()["contract"]["products"][0]

        self.assertEqual(product_entry["product_id"], self.product.pk)
        self.assertEqual(product_entry["internal_code"], "PROD-001")
        self.assertEqual(product_entry["external_designation"], "DOLI1000")

    def test_returns_empty_products_list_when_contract_has_none(self):
        """A contract with no linked products must return an empty list, not an error."""
        account = make_account(code="PH-005")
        make_contract(account, status=STATUS_ACTIVE)

        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-005"}
        )
        products = response.json()["contract"]["products"]
        self.assertEqual(products, [])

    def test_returns_all_products_when_contract_has_multiple(self):
        """All products linked to the active contract must appear in the response."""
        second_product = make_product(
            code="PROD-002",
            designation="Amoxicilline 500mg",
        )
        Contract_Product.objects.create(
            contract=self.contract,
            product=second_product,
            external_designation="AMOX500",
        )

        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-001"}
        )
        products = response.json()["contract"]["products"]
        self.assertEqual(len(products), 2)

    def test_inactive_contract_is_never_returned(self):
        """
        When an account has both active and inactive contracts,
        only the active one must be returned.
        This guards against a future regression where status filtering breaks.
        """
        # The active contract exists from setUp.
        # Create a second account that has ONLY an inactive contract.
        account = make_account(code="PH-006")
        make_contract(account, status=STATUS_INACTIVE)

        response = self.auth_client.get(
            self.API_URL, {"account_code": "PH-006"}
        )
        self.assertEqual(response.status_code, 404)

    # -----------------------------------------------------------------------
    # Token tracking tests
    # -----------------------------------------------------------------------

    def test_usage_count_increments_on_successful_request(self):
        """
        Each successful authenticated request must increment usage_count.
        This allows admins to monitor API usage per token.
        """
        initial_count = self.token.usage_count

        self.auth_client.get(self.API_URL, {"account_code": "PH-001"})

        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, initial_count + 1)

    def test_usage_count_increments_multiple_times(self):
        """usage_count must increment correctly across multiple calls."""
        for _ in range(3):
            self.auth_client.get(self.API_URL, {"account_code": "PH-001"})

        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, 3)

    def test_last_used_at_is_none_before_first_request(self):
        """A freshly created token must have last_used_at = None."""
        fresh_token = make_api_token(name="Fresh Token")
        self.assertIsNone(fresh_token.last_used_at)

    def test_last_used_at_is_set_after_first_request(self):
        """last_used_at must be populated after the first authenticated request."""
        self.assertIsNone(self.token.last_used_at)

        self.auth_client.get(self.API_URL, {"account_code": "PH-001"})

        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_usage_count_does_not_increment_for_invalid_token(self):
        """
        A request with an invalid token must not update any token's usage_count.
        Rejected requests must never be counted as usage.
        """
        bad_client = APIClient()
        bad_client.credentials(HTTP_AUTHORIZATION="Token notavalidtoken")
        bad_client.get(self.API_URL, {"account_code": "PH-001"})

        self.token.refresh_from_db()
        self.assertEqual(self.token.usage_count, 0)
