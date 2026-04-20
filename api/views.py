"""
api/views.py
------------
REST API views for the FIDPHA public API (v1).

Thin view classes — HTTP concerns only:
  - Parse and validate request parameters / body
  - Call service functions
  - Map service exceptions to HTTP error responses
  - Return structured JSON responses

No business logic or database queries live here.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from fidpha.services import (
    AccountNotFoundError,
    ContractNotFoundError,
    get_active_contract,
    get_contract_products,
)
from sales.services import (
    BatchTooLargeError,
    confirm_sync,
    submit_sales_batch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    return timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _error(code: str, message: str, http_status: int) -> Response:
    """Return a consistent error envelope."""
    return Response(
        {
            "status":    "error",
            "timestamp": _timestamp(),
            "error": {"code": code, "message": message},
        },
        status=http_status,
    )


def _parse_dt(value: str | None):
    """
    Parse an ISO 8601 datetime string from the request body.
    Returns a timezone-aware datetime or None if value is missing/invalid.

    Naive datetimes (no TZ offset in the string) are treated as UTC, which
    is the standard convention for REST API timestamps.
    """
    if not value:
        return None
    dt = parse_datetime(str(value))
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Custom exception handler
# ---------------------------------------------------------------------------

def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    Global DRF exception handler — returns a consistent error envelope
    for authentication failures. All other exceptions use DRF's default.
    """
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return Response(
            {
                "status":    "error",
                "timestamp": _timestamp(),
                "error": {
                    "code":    "INVALID_TOKEN",
                    "message": "Missing or invalid token",
                },
            },
            status=401,
        )
    return exception_handler(exc, context)


# ---------------------------------------------------------------------------
# Endpoint 1 — GET /api/v1/contract/active/
# ---------------------------------------------------------------------------

class ActiveContractView(APIView):
    """
    Retrieve the active contract for a given pharmacy account.

    Query Parameters:
        account_code (str): The unique pharmacy account code.

    Success Response (200):
        {
            "status": "success",
            "timestamp": "...",
            "contract": {
                "contract_id": 1,
                "contract_title": "C001",
                "pharmacy": "PHARMACY SAADA",
                "account_code": "PH-XXXXX",
                "start_date": "2026-04-07",
                "end_date": "2026-05-07",
                "last_sale_datetime": "2026-04-17T14:45:00" | null,
                "last_sync_at": "2026-04-17T09:14:00" | null,
                "products": [
                    {
                        "product_id": 1,
                        "internal_code": "PROD001",
                        "external_designation": "DOLI1000",
                        "designation": "Doliprane paracetamol 1000mg"
                    }
                ]
            }
        }

    Error Responses:
        400 MISSING_PARAMETER  — account_code not provided
        404 ACCOUNT_NOT_FOUND  — no account with that code
        404 CONTRACT_NOT_FOUND — account has no active contract
        401 INVALID_TOKEN      — bad or missing token
    """

    def get(self, request, version: str = None) -> Response:
        account_code = request.query_params.get("account_code")

        if not account_code:
            return _error("MISSING_PARAMETER", "The account_code parameter is missing", 400)

        try:
            contract = get_active_contract(account_code)
        except AccountNotFoundError:
            return _error(
                "ACCOUNT_NOT_FOUND",
                f"No account found with code '{account_code}'",
                404,
            )
        except ContractNotFoundError:
            return _error(
                "CONTRACT_NOT_FOUND",
                f"No active contract found for account '{account_code}'",
                404,
            )

        products = get_contract_products(contract)

        return Response(
            {
                "status":    "success",
                "timestamp": _timestamp(),
                "contract": {
                    "contract_id":    contract.pk,
                    "contract_title": contract.title,
                    "pharmacy":       contract.account.name,
                    "account_code":   contract.account.code,
                    "start_date":     contract.start_date.strftime("%Y-%m-%d"),
                    "end_date":       contract.end_date.strftime("%Y-%m-%d"),
                    "last_sale_datetime": (
                        contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S")
                        if contract.last_sale_datetime else None
                    ),
                    "last_sync_at": (
                        contract.last_sync_at.strftime("%Y-%m-%dT%H:%M:%S")
                        if contract.last_sync_at else None
                    ),
                    "products": products,
                },
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Endpoint 2 — POST /api/v1/sales/
# ---------------------------------------------------------------------------

class SalesSubmitView(APIView):
    """
    Submit a batch of sales rows for a pharmacy account.

    Request Body:
        {
            "account_code": "PH-001",
            "batch_id": "BATCH-20260418-001",
            "sales": [
                {
                    "external_designation": "AMOX500",
                    "sale_datetime": "2026-04-17T09:30:00",
                    "creation_datetime": "2026-04-17T23:00:00",
                    "quantity": 5,
                    "ppv": 12.50
                }
            ]
        }

    Success Response (200):
        {
            "batch_id": "BATCH-20260418-001",
            "received": 2,
            "accepted": 1,
            "rejected": 1,
            "errors": [
                {
                    "index": 1,
                    "external_designation": "UNKNOWN",
                    "reason": "Product not found in active contract"
                }
            ]
        }
    """

    def post(self, request, version: str = None) -> Response:
        data         = request.data
        account_code = data.get("account_code", "").strip()
        batch_id     = data.get("batch_id", "").strip()
        sales_data   = data.get("sales", [])

        # ── Basic request validation ──
        if not account_code:
            return _error("MISSING_FIELD", "account_code is required", 400)
        if not batch_id:
            return _error("MISSING_FIELD", "batch_id is required", 400)
        if not isinstance(sales_data, list) or len(sales_data) == 0:
            return _error("MISSING_FIELD", "sales must be a non-empty list", 400)

        # ── Parse datetime fields on each row ──
        parsed_sales = []
        parse_errors = []

        for idx, row in enumerate(sales_data):
            sale_dt     = _parse_dt(row.get("sale_datetime"))
            creation_dt = _parse_dt(row.get("creation_datetime"))

            missing = []
            if not row.get("external_designation"):
                missing.append("external_designation")
            if sale_dt is None:
                missing.append("sale_datetime")
            if creation_dt is None:
                missing.append("creation_datetime")
            if row.get("quantity") is None:
                missing.append("quantity")
            if row.get("ppv") is None:
                missing.append("ppv")

            if missing:
                parse_errors.append({
                    "index":  idx,
                    "reason": f"Missing or invalid fields: {', '.join(missing)}",
                })
                continue

            parsed_sales.append({
                "external_designation": row["external_designation"],
                "sale_datetime":        sale_dt,
                "creation_datetime":    creation_dt,
                "quantity":             int(row["quantity"]),
                "ppv":                  float(row["ppv"]),
            })

        if parse_errors:
            return Response(
                {
                    "status":  "error",
                    "message": "One or more rows have missing or invalid fields.",
                    "errors":  parse_errors,
                },
                status=400,
            )

        # ── Delegate to service ──
        try:
            result = submit_sales_batch(
                account_code=account_code,
                batch_id=batch_id,
                sales_data=parsed_sales,
                token=request.auth,
            )
        except BatchTooLargeError as exc:
            return _error("BATCH_TOO_LARGE", str(exc), 400)
        except AccountNotFoundError:
            return _error(
                "ACCOUNT_NOT_FOUND",
                f"No account found with code '{account_code}'",
                404,
            )
        except ContractNotFoundError:
            return _error(
                "CONTRACT_NOT_FOUND",
                f"No active contract found for account '{account_code}'",
                404,
            )
        except Exception:
            return _error("SERVER_ERROR", "An unexpected error occurred.", 500)

        return Response(result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Endpoint 3 — POST /api/v1/contract/sync/
# ---------------------------------------------------------------------------

class ContractSyncView(APIView):
    """
    Pharmacy confirms it has finished syncing its sales batch.

    Sets last_sync_at on the contract and cross-checks the reported
    last_sale_datetime against what we actually accepted.

    Request Body:
        {
            "account_code": "PH-001",
            "batch_id": "BATCH-20260418-001",
            "last_sale_datetime": "2026-04-17T14:45:00"
        }

    Success Response (200):
        {
            "contract_id": 1,
            "last_sync_at": "2026-04-18T09:14:00Z",
            "last_sale_datetime": "2026-04-17T14:45:00",
            "sync_status": "ok" | "warning",
            "mismatch": false | true,
            "detail": "..." (only when mismatch=true)
        }
    """

    def post(self, request, version: str = None) -> Response:
        data         = request.data
        account_code = data.get("account_code", "").strip()
        batch_id     = data.get("batch_id", "").strip()
        reported_dt  = _parse_dt(data.get("last_sale_datetime"))

        if not account_code:
            return _error("MISSING_FIELD", "account_code is required", 400)
        if not batch_id:
            return _error("MISSING_FIELD", "batch_id is required", 400)

        try:
            result = confirm_sync(
                account_code=account_code,
                batch_id=batch_id,
                pharmacy_last_sale_datetime=reported_dt,
            )
        except AccountNotFoundError:
            return _error(
                "ACCOUNT_NOT_FOUND",
                f"No account found with code '{account_code}'",
                404,
            )
        except ContractNotFoundError:
            return _error(
                "CONTRACT_NOT_FOUND",
                f"No active contract found for account '{account_code}'",
                404,
            )

        return Response(result, status=status.HTTP_200_OK)
