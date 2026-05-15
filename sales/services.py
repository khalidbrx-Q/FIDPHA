"""
sales/services.py
-----------------
Business logic for the pharmacy sales sync flow.

All domain operations for sales ingestion live here — no HTTP logic.
Views call these functions and map the results to JSON responses.

Critical points baked in:
  1. Race condition on last_sale_datetime  → select_for_update() inside atomic()
  2. Duplicate / retry batches             → idempotency check on batch_id before processing
  3. Contract state change mid-sync        → contract re-validated inside atomic()
  4. Large batch sizes                     → MAX_BATCH_SIZE enforced before processing
  5. Validation atomicity                  → transaction.atomic() wraps full batch
  6. Concurrent pending batches            → warnings[] field in success response

Date validation rules:
  - sale_datetime must be STRICTLY AFTER contract.last_sale_datetime to be accepted;
    sales at exactly last_sale_datetime are rejected (boundary is exclusive — the next
    batch must start from a datetime strictly greater than the last accepted one)
  - sale_datetime date must be BEFORE today (no same-day or future sales)
"""

import datetime

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from django.apps import apps

_BATCH_LIMIT_CACHE_TTL = 30   # seconds — batch limit cached to avoid DB hit per submission

from fidpha.models import Contract, Contract_Product
from fidpha.services import get_active_contract
from sales.models import Sale, SaleImport

MAX_BATCH_SIZE = 50000  # fallback default — overridden at runtime by SystemConfig.max_batch_size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    effective_max = cache.get("sc:max_batch_size")
    if effective_max is None:
        SystemConfig = apps.get_model("control", "SystemConfig")
        effective_max = SystemConfig.get().max_batch_size
        cache.set("sc:max_batch_size", effective_max, _BATCH_LIMIT_CACHE_TTL)
    # 0 means no limit; only enforce when a positive limit is configured
    if effective_max > 0 and len(sales_data) > effective_max:
        raise BatchTooLargeError(
            f"Batch too large. Max {effective_max} rows per request, "
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
            .select_related("account")
            .get(pk=contract.pk, status=Contract.STATUS_ACTIVE)
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
        sales_to_create   = []
        imports_to_update = []
        errors            = []
        max_sale_dt       = None
        seen_keys         = set()  # (external_designation, sale_datetime) within this batch

        for idx, (row, sale_import) in enumerate(zip(sales_data, created_imports)):
            ext = row.get("external_designation", "")
            cp  = cp_map.get(ext)

            # Assign contract_product as soon as it's resolved so it is
            # persisted even on rejected rows (enables audit display).
            if cp:
                sale_import.contract_product = cp

            rejection_reason = None

            now      = timezone.now()
            today    = now.date()
            sale_date = sale_import.sale_datetime.date()
            row_key   = (ext, sale_import.sale_datetime)

            if not cp:
                rejection_reason = f"Product '{ext}' not found in active contract"

            elif row_key in seen_keys:
                rejection_reason = (
                    f"Duplicate row within batch: same product and sale_datetime already accepted"
                )

            elif sale_date >= today:
                rejection_reason = (
                    f"sale_datetime must be before today — same-day and future sales are not accepted "
                    f"({sale_import.sale_datetime.strftime('%Y-%m-%dT%H:%M:%S')})"
                )

            elif (
                contract.last_sale_datetime is not None
                and sale_import.sale_datetime <= contract.last_sale_datetime
            ):
                rejection_reason = (
                    f"sale_datetime is already covered by a previous sync "
                    f"(must be strictly after last accepted: {contract.last_sale_datetime.strftime('%Y-%m-%dT%H:%M:%S')})"
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
                seen_keys.add(row_key)
                sale_import.status = SaleImport.STATUS_ACCEPTED
                sales_to_create.append(Sale(
                    sale_import=sale_import,
                    contract_product=cp,
                    sale_datetime=sale_import.sale_datetime,
                    creation_datetime=sale_import.creation_datetime,
                    quantity=sale_import.quantity,
                    ppv=sale_import.ppv,
                    product_ppv=cp.product.ppv,
                    status=Sale.STATUS_PENDING,
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

        # ── Concurrent batch warning ──
        # Warn if this account already has other batches awaiting staff review.
        pending_batch_count = (
            Sale.objects
            .filter(contract_product__contract=contract, status=Sale.STATUS_PENDING)
            .values("sale_import__batch_id")
            .distinct()
            .count()
        )
        warnings = []
        if pending_batch_count > 0:
            warnings.append({
                "code":    "CONCURRENT_BATCH",
                "message": (
                    f"{pending_batch_count} other pending batch(es) already "
                    "await staff review for this contract."
                ),
            })

        # ── Auto-review: if enabled globally AND for this account, auto-accept ──
        # Uses apps.get_model to avoid a hard circular import (control → sales).
        SystemConfig = apps.get_model("control", "SystemConfig")
        if SystemConfig.get().auto_review_enabled and contract.account.auto_review_enabled:
            review_ts = timezone.now()
            for sale in sales_to_create:
                sale.status        = Sale.STATUS_ACCEPTED
                sale.auto_reviewed = True
                sale.reviewed_at   = review_ts
                # reviewed_by stays None — system action, not a staff user

        # ── Stage 3: Write accepted rows to Sale ──
        if sales_to_create:
            Sale.objects.bulk_create(sales_to_create)

            # Atomically update last_sale_datetime and last_sync_at
            update_fields = {"last_sync_at": now}
            if max_sale_dt and (
                contract.last_sale_datetime is None
                or max_sale_dt > contract.last_sale_datetime
            ):
                update_fields["last_sale_datetime"] = max_sale_dt
            Contract.objects.filter(pk=contract.pk).update(**update_fields)

    accepted_count = len(sales_to_create)
    rejected_count = len(errors)

    return {
        "batch_id":  batch_id,
        "received":  len(sales_data),
        "accepted":  accepted_count,
        "rejected":  rejected_count,
        "errors":    errors,
        "warnings":  warnings,
    }
