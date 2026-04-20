"""
sales/services.py
-----------------
Business logic for the pharmacy sales sync flow.

All domain operations for sales ingestion live here — no HTTP logic.
Views call these functions and map the results to JSON responses.

Critical points baked in:
  1. Race condition on last_sale_datetime  → select_for_update() inside atomic()
  2. Duplicate / retry batches             → bulk_create(ignore_conflicts=True)
  3. Contract state change mid-sync        → contract re-validated inside atomic()
  4. Large batch sizes                     → MAX_BATCH_SIZE enforced before processing
  5. Concurrent batches — pending warning  → checked in confirm_sync()
  6. Validation atomicity                  → transaction.atomic() wraps full batch
"""

import datetime

from django.db import transaction
from django.utils import timezone

from fidpha.models import Contract, Contract_Product
from fidpha.services import get_active_contract
from sales.models import Sale, SaleImport

MAX_BATCH_SIZE = 5000


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BatchTooLargeError(Exception):
    pass


# ---------------------------------------------------------------------------
# Endpoint 2 — Submit sales batch
# ---------------------------------------------------------------------------

def submit_sales_batch(
    account_code: str,
    batch_id: str,
    sales_data: list,
    token,
) -> dict:
    """
    Process a batch of pharmacy sales rows.

    Stage 1: Insert all rows into SaleImport (status=pending).
    Stage 2: Validate each row and resolve its contract product.
    Stage 3: Write accepted rows to Sale; update Contract.last_sale_datetime.

    Args:
        account_code: The pharmacy account code.
        batch_id:     Client-generated batch identifier.
        sales_data:   List of dicts from the request body.
        token:        The APIToken used for this request (for traceability).

    Returns:
        Dict with batch_id, received, accepted, rejected, errors.

    Raises:
        BatchTooLargeError:     If len(sales_data) > MAX_BATCH_SIZE.
        AccountNotFoundError:   If account_code doesn't match any account.
        ContractNotFoundError:  If account has no active contract.
    """
    if len(sales_data) > MAX_BATCH_SIZE:
        raise BatchTooLargeError(
            f"Batch too large. Max {MAX_BATCH_SIZE} rows per request, "
            f"got {len(sales_data)}."
        )

    # Validate account + contract before touching any data
    # Raises AccountNotFoundError / ContractNotFoundError if invalid
    contract = get_active_contract(account_code)

    # Pre-fetch all contract products into a lookup map to avoid N+1 queries
    cp_map: dict[str, Contract_Product] = {
        cp.external_designation: cp
        for cp in Contract_Product.objects.filter(
            contract=contract
        ).select_related("product")
    }

    with transaction.atomic():
        # ── Re-validate contract is still active inside the transaction ──
        # Protects against the contract being deactivated between the check
        # above and the actual write below.
        contract = (
            Contract.objects
            .select_for_update()
            .get(pk=contract.pk, status="active")
        )

        # ── Stage 1: Insert all rows to SaleImport (status=pending) ──
        imports_to_create = []
        for row in sales_data:
            imports_to_create.append(SaleImport(
                batch_id=batch_id,
                account_code=account_code,
                external_designation=row.get("external_designation", ""),
                sale_datetime=row.get("sale_datetime"),
                creation_datetime=row.get("creation_datetime"),
                quantity=row.get("quantity", 0),
                ppv=row.get("ppv", 0),
                status=SaleImport.STATUS_PENDING,
                token=token,
            ))

        created_imports = SaleImport.objects.bulk_create(imports_to_create)

        # ── Stage 2: Validate each row ──
        sales_to_create  = []
        imports_to_update = []
        errors           = []
        max_sale_dt      = None

        for idx, (row, sale_import) in enumerate(zip(sales_data, created_imports)):
            ext = row.get("external_designation", "")
            cp  = cp_map.get(ext)

            rejection_reason = None

            now = timezone.now()

            if not cp:
                rejection_reason = f"Product '{ext}' not found in active contract"

            elif sale_import.sale_datetime > now:
                rejection_reason = (
                    f"sale_datetime is in the future "
                    f"({sale_import.sale_datetime.strftime('%Y-%m-%dT%H:%M:%S')})"
                )

            elif sale_import.creation_datetime > now:
                rejection_reason = (
                    f"creation_datetime is in the future "
                    f"({sale_import.creation_datetime.strftime('%Y-%m-%dT%H:%M:%S')})"
                )

            elif sale_import.creation_datetime < sale_import.sale_datetime:
                rejection_reason = (
                    "creation_datetime cannot be before sale_datetime"
                )

            elif sale_import.sale_datetime < contract.start_date:
                rejection_reason = (
                    f"sale_datetime is before contract start "
                    f"({contract.start_date.strftime('%Y-%m-%d')})"
                )

            elif sale_import.sale_datetime > contract.end_date:
                rejection_reason = (
                    f"sale_datetime is after contract end "
                    f"({contract.end_date.strftime('%Y-%m-%d')})"
                )

            elif sale_import.quantity <= 0:
                rejection_reason = "quantity must be greater than 0"

            elif sale_import.ppv <= 0:
                rejection_reason = "ppv must be greater than 0"

            if rejection_reason:
                sale_import.status           = SaleImport.STATUS_REJECTED
                sale_import.rejection_reason = rejection_reason
                errors.append({
                    "index":                idx,
                    "external_designation": ext,
                    "reason":               rejection_reason,
                })
            else:
                sale_import.status           = SaleImport.STATUS_ACCEPTED
                sale_import.contract_product = cp
                sales_to_create.append(Sale(
                    sale_import=sale_import,
                    contract_product=cp,
                    sale_datetime=sale_import.sale_datetime,
                    creation_datetime=sale_import.creation_datetime,
                    quantity=sale_import.quantity,
                    ppv=sale_import.ppv,
                    token=token,
                ))
                if max_sale_dt is None or sale_import.sale_datetime > max_sale_dt:
                    max_sale_dt = sale_import.sale_datetime

            imports_to_update.append(sale_import)

        # Bulk-update all SaleImport rows with final status / reason / cp
        SaleImport.objects.bulk_update(
            imports_to_update,
            ["status", "rejection_reason", "contract_product"],
        )

        # ── Stage 3: Write accepted rows to Sale ──
        if sales_to_create:
            # ignore_conflicts=True handles retries — duplicate rows
            # (same contract_product + sale_datetime) are silently skipped
            Sale.objects.bulk_create(sales_to_create, ignore_conflicts=True)

            # Atomically update last_sale_datetime — select_for_update() above
            # already holds the row lock, so this plain update is race-free
            if max_sale_dt and (
                contract.last_sale_datetime is None
                or max_sale_dt > contract.last_sale_datetime
            ):
                Contract.objects.filter(pk=contract.pk).update(
                    last_sale_datetime=max_sale_dt
                )

    accepted_count = len(sales_to_create)
    rejected_count = len(errors)

    return {
        "batch_id":  batch_id,
        "received":  len(sales_data),
        "accepted":  accepted_count,
        "rejected":  rejected_count,
        "errors":    errors,
    }


# ---------------------------------------------------------------------------
# Endpoint 3 — Confirm sync
# ---------------------------------------------------------------------------

def confirm_sync(
    account_code: str,
    batch_id: str,
    pharmacy_last_sale_datetime,
) -> dict:
    """
    Stamp last_sync_at on the contract and cross-check the reported datetime.

    Args:
        account_code:                  The pharmacy account code.
        batch_id:                      The batch being confirmed.
        pharmacy_last_sale_datetime:   The last sale datetime the pharmacy reports.

    Returns:
        Dict with contract_id, last_sync_at, last_sale_datetime,
        sync_status, mismatch, and optional detail / pending_warning.
    """
    contract = get_active_contract(account_code)
    now      = timezone.now()

    Contract.objects.filter(pk=contract.pk).update(last_sync_at=now)
    contract.refresh_from_db()

    # Cross-check: compare what pharmacy reported vs what we accepted
    mismatch = False
    detail   = None

    if pharmacy_last_sale_datetime and contract.last_sale_datetime:
        if pharmacy_last_sale_datetime.replace(microsecond=0) != contract.last_sale_datetime.replace(microsecond=0):
            mismatch = True
            detail = (
                f"You reported "
                f"{pharmacy_last_sale_datetime.strftime('%Y-%m-%dT%H:%M:%S')} "
                f"but we only accepted up to "
                f"{contract.last_sale_datetime.strftime('%Y-%m-%dT%H:%M:%S')}. "
                f"Some rows may have been rejected."
            )

    # Warn if there are still pending rows for this batch
    pending_count = SaleImport.objects.filter(
        batch_id=batch_id,
        account_code=account_code,
        status=SaleImport.STATUS_PENDING,
    ).count()

    has_warning  = mismatch or pending_count > 0
    sync_status  = "warning" if has_warning else "ok"

    result: dict = {
        "contract_id":        contract.pk,
        "last_sync_at":       now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_sale_datetime": (
            contract.last_sale_datetime.strftime("%Y-%m-%dT%H:%M:%S")
            if contract.last_sale_datetime else None
        ),
        "sync_status": sync_status,
        "mismatch":    mismatch,
    }

    if mismatch:
        result["detail"] = detail

    if pending_count > 0:
        result["pending_warning"] = (
            f"{pending_count} rows from batch '{batch_id}' are still pending."
        )

    return result
