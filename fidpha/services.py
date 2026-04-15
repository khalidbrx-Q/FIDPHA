"""
fidpha/services.py
------------------
Business logic layer for the fidpha app.

This module acts as the single source of truth for all domain operations
related to Accounts, Contracts, and Products. It is intentionally kept
free of any HTTP-specific logic (no HttpRequest, no JsonResponse) so that
it can be called from any context: API views, admin helpers, management
commands, or tests.

Consumers of this module should catch the custom exceptions defined here
and translate them into the appropriate HTTP responses on their side.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from fidpha.models import Account, Contract, Contract_Product, Product
from django.db.models import QuerySet


# ---------------------------------------------------------------------------
# Status constants
# Using named constants instead of magic strings makes the intent explicit
# and prevents typos from silently producing wrong query results.
# ---------------------------------------------------------------------------

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"


# ---------------------------------------------------------------------------
# Custom exceptions
# Defining domain-specific exceptions lets callers handle errors with
# precision (e.g. map AccountNotFoundError → 404) without coupling the
# service layer to HTTP status codes.
# ---------------------------------------------------------------------------

class AccountNotFoundError(Exception):
    """Raised when no Account matches the given account code."""
    pass


class ContractNotFoundError(Exception):
    """Raised when no active Contract exists for a given account."""
    pass


class ProductNotFoundError(Exception):
    """Raised when no active Product matches the given product ID."""
    pass


class ProductAlreadyLinkedError(Exception):
    """Raised when a product is already linked to the target contract."""
    pass


# ---------------------------------------------------------------------------
# Account services
# ---------------------------------------------------------------------------

def get_account(account_code: str) -> Account:
    """
    Retrieve an Account by its unique pharmacy code.

    This is the canonical way to look up an account. It should be used
    by any caller that needs an Account object, so the lookup logic lives
    in exactly one place.

    Args:
        account_code (str): The unique pharmacy account code (e.g. 'PH-XXXXX').

    Returns:
        Account: The matching Account instance.

    Raises:
        AccountNotFoundError: If no Account with the given code exists
            in the database.
    """
    try:
        return Account.objects.get(code=account_code)
    except Account.DoesNotExist:
        raise AccountNotFoundError(
            f"No account found with code '{account_code}'."
        )


# ---------------------------------------------------------------------------
# Contract services
# ---------------------------------------------------------------------------

def get_active_contract(account_code: str) -> Contract:
    """
    Retrieve the active Contract for a given pharmacy account.

    Each account may have at most one active contract at a time (enforced
    by the business rule in Contract.clean()). This function first resolves
    the account by code, then fetches its single active contract.

    Args:
        account_code (str): The unique pharmacy account code (e.g. 'PH-XXXXX').

    Returns:
        Contract: The active Contract instance linked to the account.

    Raises:
        AccountNotFoundError: If no Account with the given code exists.
        ContractNotFoundError: If the account exists but has no active contract.
    """
    # Resolve the account first — raises AccountNotFoundError if missing
    account = get_account(account_code)

    try:
        return Contract.objects.get(account=account, status=STATUS_ACTIVE)
    except Contract.DoesNotExist:
        raise ContractNotFoundError(
            f"No active contract found for account '{account_code}'."
        )


def get_contract_products(contract: Contract) -> list[dict]:
    """
    Build the list of product entries for a given contract.

    Each entry maps a product's internal code to its external designation
    as defined in the Contract_Product junction record. This separation
    allows pharmacies to use their own naming conventions for products.

    Args:
        contract (Contract): The contract whose products should be returned.

    Returns:
        list[dict]: A list of dicts, each containing:
            - product_id (int): Primary key of the product.
            - internal_code (str): The product's internal code in FIDPHA.
            - external_designation (str): The pharmacy-specific product name.
    """
    products = []

    for contract_product in contract.contract_product_set.all():
        products.append({
            "product_id": contract_product.product.pk,
            "internal_code": contract_product.product.code,
            "external_designation": contract_product.external_designation,
        })

    return products


# ---------------------------------------------------------------------------
# Admin helper services
# These are used by admin_api.py views (AJAX endpoints in the admin panel).
# They are placed here — not in admin.py — so they remain testable and
# reusable outside the admin context if needed.
# ---------------------------------------------------------------------------

def get_available_products_for_contract(contract_id: int) -> QuerySet:
    """
    Return all active products that are not yet linked to the given contract.

    Used by the admin panel's "Add Product" modal to populate the product
    search dropdown. We exclude already-linked products to prevent duplicate
    entries in the Contract_Product table.

    Args:
        contract_id (int): The primary key of the target contract.

    Returns:
        QuerySet: A queryset of Product instances that are active and not
            yet linked to this contract, ordered alphabetically by designation.

    Raises:
        Contract.DoesNotExist: If no contract with the given ID exists.
            The caller (admin_api.py) is responsible for handling this.
    """
    contract = Contract.objects.get(pk=contract_id)

    # Collect IDs of products already attached to this contract
    # to exclude them from the available list and prevent duplicates
    already_linked_product_ids = Contract_Product.objects.filter(
        contract=contract
    ).values_list("product_id", flat=True)

    return Product.objects.filter(
        status=STATUS_ACTIVE
    ).exclude(
        id__in=already_linked_product_ids
    ).order_by("designation")


def get_active_contracts_for_product(product: Product) -> QuerySet:
    """
    Return all active contracts that include the given product.

    Used when attempting to deactivate a product — if this queryset is
    non-empty, deactivation must be blocked to preserve contract integrity
    (Business Rule 2).

    Args:
        product (Product): The product to check.

    Returns:
        QuerySet: A queryset of Contract instances that are active and
            contain this product, with their related account pre-fetched.
    """
    return Contract.objects.filter(
        contract_product__product=product,
        status=STATUS_ACTIVE
    ).select_related("account")


def link_product_to_contract(
    contract_id: int,
    product_id: int,
    external_designation: str,
) -> Contract_Product:
    """
    Link an active product to a contract with a pharmacy-specific designation.

    This is the single place where Contract_Product records are created via
    the admin panel. It validates that both the contract and product exist,
    that the product is active, and that the link does not already exist.

    Args:
        contract_id (int): Primary key of the target contract.
        product_id (int): Primary key of the product to link.
        external_designation (str): The pharmacy's own name for this product.

    Returns:
        Contract_Product: The newly created junction record.

    Raises:
        Contract.DoesNotExist: If no contract with the given ID exists.
        ProductNotFoundError: If no active product with the given ID exists.
        ProductAlreadyLinkedError: If the product is already linked to
            this contract.
    """
    contract = Contract.objects.get(pk=contract_id)

    try:
        product = Product.objects.get(pk=product_id, status=STATUS_ACTIVE)
    except Product.DoesNotExist:
        raise ProductNotFoundError(
            f"No active product found with ID {product_id}."
        )

    # Guard against duplicate links — the DB has a unique_together constraint,
    # but we raise a meaningful error before hitting it
    if Contract_Product.objects.filter(contract=contract, product=product).exists():
        raise ProductAlreadyLinkedError(
            f"Product '{product.designation}' is already linked to "
            f"contract '{contract.title}'."
        )

    return Contract_Product.objects.create(
        contract=contract,
        product=product,
        external_designation=external_designation,
    )
