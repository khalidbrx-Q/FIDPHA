"""
api/views.py
------------
REST API views for the FIDPHA public API (v1).

This module contains thin view classes that handle HTTP concerns only:
- Parsing and validating request parameters
- Calling the appropriate service functions from fidpha.services
- Mapping service exceptions to HTTP error responses
- Formatting and returning JSON responses

No business logic or database queries should live here.
All domain operations are delegated to fidpha/services.py.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from django.utils import timezone

from rest_framework.views import APIView, exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

from fidpha.services import (
    get_active_contract,
    get_contract_products,
    AccountNotFoundError,
    ContractNotFoundError,
)


# ---------------------------------------------------------------------------
# Custom exception handler
# ---------------------------------------------------------------------------

def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    Global DRF exception handler for the FIDPHA API.

    Overrides DRF's default handler to return a consistent error envelope
    for authentication failures. All other exceptions fall through to
    DRF's default handler.

    Registered in settings.py under:
        REST_FRAMEWORK["EXCEPTION_HANDLER"]

    Args:
        exc (Exception): The exception raised by the view.
        context (dict): DRF context dict containing the request and view.

    Returns:
        Response | None: A structured error Response for auth errors,
            or the result of DRF's default handler for everything else.
    """
    timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Return a consistent auth error envelope instead of DRF's default format
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return Response(
            {
                "status": "error",
                "timestamp": timestamp,
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "Missing or invalid token",
                },
            },
            status=401,
        )

    return exception_handler(exc, context)


# ---------------------------------------------------------------------------
# Contract views
# ---------------------------------------------------------------------------

class ActiveContractView(APIView):
    """
    Retrieve the active contract for a given pharmacy account.

    Endpoint:
        GET /api/v1/contract/active/?account_code=PH-XXXXX

    Authentication:
        Required — Authorization: Token <token> header.

    Query Parameters:
        account_code (str): The unique pharmacy account code.

    Success Response (200):
        {
            "status": "success",
            "timestamp": "2026-04-13T14:30:00Z",
            "contract": {
                "id": 1,
                "pharmacy": "PHARMACY SAADA",
                "account_code": "PH-XXXXX",
                "start_date": "2026-04-07",
                "end_date": "2026-05-07",
                "products": [
                    {
                        "product_id": 1,
                        "internal_code": "PROD001",
                        "external_designation": "DOLI1000"
                    }
                ]
            }
        }

    Error Responses:
        400 MISSING_PARAMETER  — account_code query param not provided
        404 ACCOUNT_NOT_FOUND  — no account with the given code
        404 CONTRACT_NOT_FOUND — account exists but has no active contract
    """

    def get(self, request, version: str = None) -> Response:
        """
        Handle GET requests for the active contract endpoint.

        Args:
            request: The DRF request object.
            version (str): API version from URL path versioning (e.g. 'v1').

        Returns:
            Response: A DRF Response with the contract data or an error envelope.
        """
        timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        account_code = request.query_params.get("account_code")

        # Validate that the required query parameter was provided
        if not account_code:
            return Response(
                {
                    "status": "error",
                    "timestamp": timestamp,
                    "error": {
                        "code": "MISSING_PARAMETER",
                        "message": "The account_code parameter is missing",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Delegate all business logic to the service layer —
            # this view has no knowledge of how accounts or contracts
            # are stored or validated
            contract = get_active_contract(account_code)

        except AccountNotFoundError:
            return Response(
                {
                    "status": "error",
                    "timestamp": timestamp,
                    "error": {
                        "code": "ACCOUNT_NOT_FOUND",
                        "message": f"No account found with code '{account_code}'",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except ContractNotFoundError:
            return Response(
                {
                    "status": "error",
                    "timestamp": timestamp,
                    "error": {
                        "code": "CONTRACT_NOT_FOUND",
                        "message": (
                            f"No active contract found for account '{account_code}'"
                        ),
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Build the product list via the service — the view stays thin
        products = get_contract_products(contract)

        return Response(
            {
                "status": "success",
                "timestamp": timestamp,
                "contract": {
                    "id": contract.pk,
                    "pharmacy": contract.account.name,
                    "account_code": contract.account.code,
                    "start_date": contract.start_date.strftime("%Y-%m-%d"),
                    "end_date": contract.end_date.strftime("%Y-%m-%d"),
                    "products": products,
                },
            },
            status=status.HTTP_200_OK,
        )
