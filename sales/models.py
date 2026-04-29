"""
sales/models.py
---------------
Two-table staging design for pharmacy sales sync.

SaleImport  — raw incoming rows, always written first (staging layer).
Sale        — clean validated rows only (one-to-one back to SaleImport).

The review stamp (reviewed_by / reviewed_at) lives on SaleImport at the
batch level — when staff reviews a batch, all rows sharing the same
batch_id are stamped together.
"""

from django.contrib.auth.models import User
from django.db import models

from api.models import APIToken
from fidpha.models import Contract_Product


# ---------------------------------------------------------------------------
# SaleImport — staging layer
# ---------------------------------------------------------------------------

class SaleImport(models.Model):

    STATUS_PENDING  = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING,  "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    # ── Batch identity ──
    batch_id     = models.CharField(max_length=100)
    account_code = models.CharField(max_length=50)   # raw, as received

    # ── Raw sale fields (as sent by pharmacy) ──
    external_designation = models.CharField(max_length=255)
    sale_datetime        = models.DateTimeField()
    creation_datetime    = models.DateTimeField()
    quantity             = models.IntegerField()
    ppv                  = models.DecimalField(max_digits=10, decimal_places=2)

    # ── Resolved FK (null until validation resolves the designation) ──
    contract_product = models.ForeignKey(
        Contract_Product,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="sale_imports",
    )

    # ── Validation outcome ──
    status           = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = models.TextField(blank=True)

    # ── System / traceability ──
    received_at  = models.DateTimeField(auto_now_add=True)
    token        = models.ForeignKey(
        APIToken,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    inserted_by  = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    # ── Review stamp (batch-level — staff marks batch as reviewed) ──
    reviewed_by = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "SaleImport"
        indexes  = [
            models.Index(fields=["batch_id"]),
            models.Index(fields=["account_code", "status"]),
        ]

    def __str__(self):
        return f"[{self.status}] {self.account_code} · {self.external_designation} · {self.sale_datetime}"


# ---------------------------------------------------------------------------
# Sale — validated clean records
# ---------------------------------------------------------------------------

class Sale(models.Model):

    STATUS_PENDING  = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES  = [
        (STATUS_PENDING,  "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    # ── Traceability back to raw import ──
    sale_import = models.OneToOneField(
        SaleImport,
        on_delete=models.PROTECT,
        related_name="sale",
    )

    # ── Resolved product ──
    contract_product = models.ForeignKey(
        Contract_Product,
        on_delete=models.PROTECT,
        related_name="sales",
    )

    # ── Clean sale data (copied from SaleImport after validation) ──
    sale_datetime     = models.DateTimeField()
    creation_datetime = models.DateTimeField()
    quantity          = models.IntegerField()
    ppv               = models.DecimalField(max_digits=10, decimal_places=2)
    # Snapshot of the product's catalog PPV at the moment of insertion.
    # Decoupled from Product.ppv so future price changes don't affect
    # historical point calculations.
    product_ppv       = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # ── Staff review status ──
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_sales",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # ── System ──
    created_at  = models.DateTimeField(auto_now_add=True)
    token       = models.ForeignKey(
        APIToken,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    inserted_by = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "Sale"
        indexes = [
            models.Index(fields=["contract_product", "sale_datetime"]),
        ]

    def __str__(self):
        return f"{self.contract_product} · {self.sale_datetime} · qty={self.quantity}"
