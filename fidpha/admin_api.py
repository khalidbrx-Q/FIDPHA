"""
fidpha/admin_api.py
-------------------
AJAX endpoint functions used exclusively by the Django admin panel.

These views handle the dynamic interactions in the admin UI:
- Fetching available products when adding one to a contract (modal search)
- Adding a product to a contract via the modal form
- Toggling a product's active/inactive status with contract validation

These functions are intentionally separated from admin.py to keep the
admin registration code clean, and from api/views.py because they are
staff-only, session-authenticated endpoints — not part of the public
REST API.

All functions are registered in FIDPHA001/urls.py and protected by
an is_staff check at the view level.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

import json

from django.http import JsonResponse, HttpRequest

from fidpha.models import Contract, Contract_Product
from fidpha.services import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    get_available_products_for_contract,
    get_active_contracts_for_product,
    link_product_to_contract,
    ProductNotFoundError,
    ProductAlreadyLinkedError,
)


# ---------------------------------------------------------------------------
# Available products endpoint
# ---------------------------------------------------------------------------

def available_products_api(request: HttpRequest, contract_id: int) -> JsonResponse:
    """
    Return the list of active products not yet linked to a given contract.

    Called by the admin panel's "Add Product" modal via AJAX to populate
    the product search dropdown. Only accessible to staff users.

    Args:
        request (HttpRequest): The incoming HTTP request.
        contract_id (int): Primary key of the contract being edited.

    Returns:
        JsonResponse: 200 with a list of available products, or an error
            response (403 if not staff, 404 if contract not found).

    Response format (success):
        {
            "products": [
                {"id": 1, "code": "PROD001", "designation": "Doliprane 1000"}
            ]
        }
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        available_products = get_available_products_for_contract(contract_id)

        return JsonResponse({
            "products": [
                {
                    "id": product.pk,
                    "code": product.code,
                    "designation": product.designation,
                }
                for product in available_products
            ]
        })

    except Contract.DoesNotExist:
        return JsonResponse({"error": "Contract not found"}, status=404)


# ---------------------------------------------------------------------------
# Add product to contract endpoint
# ---------------------------------------------------------------------------

def add_contract_product_api(request: HttpRequest, contract_id: int) -> JsonResponse:
    """
    Link a product to a contract with a pharmacy-specific external designation.

    Called by the admin panel's "Add Product" modal when the staff member
    confirms their selection. Validates that the product is active and not
    already linked before creating the Contract_Product record.

    Only accessible to staff users via POST request.

    Args:
        request (HttpRequest): The incoming HTTP POST request. Expected JSON body:
            {
                "product_id": <int>,
                "external_designation": "<str>"
            }
        contract_id (int): Primary key of the contract to link the product to.

    Returns:
        JsonResponse: 200 with {"success": true} on success, or an error
            response (400, 403, 404, 405, 500) on failure.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        request_data = json.loads(request.body)
        product_id = request_data.get("product_id")
        external_designation = request_data.get("external_designation", "").strip()

        if not product_id or not external_designation:
            return JsonResponse({"error": "Missing fields"}, status=400)

        link_product_to_contract(
            contract_id=contract_id,
            product_id=int(product_id),
            external_designation=external_designation,
        )

        return JsonResponse({"success": True})

    except Contract.DoesNotExist:
        return JsonResponse({"error": "Contract not found"}, status=404)

    except ProductNotFoundError:
        return JsonResponse({"error": "Product not found or inactive"}, status=404)

    except ProductAlreadyLinkedError:
        return JsonResponse({"error": "Product already linked to this contract"}, status=400)

    except Exception as unexpected_error:
        return JsonResponse({"error": str(unexpected_error)}, status=500)


# ---------------------------------------------------------------------------
# Product status toggle endpoint
# ---------------------------------------------------------------------------

def product_toggle_api(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    Toggle a product's status between active and inactive.

    Before deactivating a product, this endpoint checks whether it is
    referenced by any active contract (Business Rule 2). If it is, the
    toggle is blocked and the conflicting contracts are returned so the
    admin user can resolve them first.

    Only accessible to staff users.

    Args:
        request (HttpRequest): The incoming HTTP request. Expected query param:
            ?status=active   or   ?status=inactive
        product_id (int): Primary key of the product to toggle.

    Returns:
        JsonResponse: On blocked deactivation:
            {
                "blocked": true,
                "product": "<designation>",
                "contracts": [
                    {
                        "id": 1,
                        "title": "...",
                        "account": "...",
                        "start_date": "...",
                        "end_date": "...",
                        "url": "/admin/fidpha/contract/1/change/"
                    }
                ]
            }
            On success:
            {
                "blocked": false,
                "new_status": "active" | "inactive"
            }
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    from fidpha.models import Product

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    requested_status = request.GET.get("status")

    # Only check for blocking contracts when deactivating —
    # activating a product never requires a conflict check
    if requested_status == STATUS_INACTIVE:
        blocking_contracts = get_active_contracts_for_product(product)

        if blocking_contracts.exists():
            # Return contract details so the admin user knows exactly
            # which contracts need to be deactivated before proceeding
            contracts_data = [
                {
                    "id": contract.pk,
                    "title": contract.title,
                    "account": contract.account.name,
                    "start_date": contract.start_date.strftime("%d %b %Y"),
                    "end_date": contract.end_date.strftime("%d %b %Y"),
                    "url": f"/admin/fidpha/contract/{contract.pk}/change/",
                }
                for contract in blocking_contracts
            ]

            return JsonResponse({
                "blocked": True,
                "product": product.designation,
                "contracts": contracts_data,
            })

    # No conflicts — safe to apply the new status
    product.status = requested_status
    product.save()

    return JsonResponse({
        "blocked": False,
        "new_status": requested_status,
    })
