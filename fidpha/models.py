from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


# -----------------------
# 0. Traceable Mixin
# -----------------------

class TraceableMixin(models.Model):
    """
    Abstract mixin that adds created_by/at and modified_by/at to any model.
    Set created_by / modified_by in views before saving; Django handles the
    timestamps automatically via auto_now_add / auto_now.
    Both FK fields are nullable so existing rows (pre-migration) stay valid.
    """
    created_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# -----------------------
# 1. Account (Pharmacie)
# -----------------------

class Account(TraceableMixin, models.Model):
    STATUS_ACTIVE   = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE,   "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    location = models.TextField()
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    pharmacy_portal     = models.BooleanField(default=False)
    auto_review_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Account"

    def __str__(self):
        return self.name

    def clean(self):
        # Rule 3: cannot deactivate account if it has at least one active contract
        if self.status == Account.STATUS_INACTIVE and self.pk:
            active_contracts = self.contracts.filter(status=Contract.STATUS_ACTIVE)
            if active_contracts.exists():
                raise ValidationError(
                    "Cannot deactivate this account because it has active contracts. "
                    "Please deactivate all contracts first."
                )


# -----------------------
# 2. UserProfile
# -----------------------

class UserProfile(TraceableMixin, models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="users")
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, null=True)
    token_created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "UserProfile"

    def __str__(self):
        return f"{self.user.username} → {self.account.name}"

# -----------------------
# 3. Product
# -----------------------

class Product(TraceableMixin, models.Model):
    STATUS_ACTIVE   = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE,   "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    code        = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=255)
    ppv         = models.DecimalField(max_digits=10, decimal_places=2)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Product"

    def __str__(self):
        return self.designation

    def clean(self):
        # Rule 2: cannot deactivate a product if it is in at least one active contract
        if self.status == Product.STATUS_INACTIVE and self.pk:
            active_contracts = Contract_Product.objects.filter(
                product=self,
                contract__status=Contract.STATUS_ACTIVE
            )
            if active_contracts.exists():
                raise ValidationError(
                    "Cannot deactivate this product because it is referenced in active contracts. "
                    "Please deactivate those contracts first."
                )


# -----------------------
# 4. Contract
# -----------------------

class Contract(TraceableMixin, models.Model):
    STATUS_ACTIVE   = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE,   "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    title = models.CharField(max_length=255)
    designation = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="contracts"
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    products = models.ManyToManyField(
        Product,
        through="Contract_Product",
        related_name="contracts"
    )

    # ── Sales sync tracking ──
    last_sync_at        = models.DateTimeField(null=True, blank=True)
    last_sale_datetime  = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Contract"

    @property
    def duration(self):
        if not self.start_date or not self.end_date:
            return ""
        days = (self.end_date.date() - self.start_date.date()).days
        if days <= 0:
            return ""
        years, rem = divmod(days, 365)
        months, d  = divmod(rem, 30)
        parts = []
        if years:  parts.append(f"{years} year{'s' if years > 1 else ''}")
        if months: parts.append(f"{months} month{'s' if months > 1 else ''}")
        if d:      parts.append(f"{d} day{'s' if d > 1 else ''}")
        return ", ".join(parts[:2])  # cap at 2 units for compactness

    def __str__(self):
        return self.title

    def clean(self):
        # Rule 5: start_date must be before or equal to end_date
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError(
                    "Start date must be before or equal to end date."
                )

        # Rule 1: only one active contract per account at a time
        if self.status == Contract.STATUS_ACTIVE and self.account_id:
            active_contracts = Contract.objects.filter(
                account=self.account,
                status=Contract.STATUS_ACTIVE
            )
            if self.pk:
                active_contracts = active_contracts.exclude(pk=self.pk)
            if active_contracts.exists():
                raise ValidationError(
                    "This account already has an active contract. "
                    "Please deactivate it before creating a new one."
                )

        # Rule 6: cannot activate a contract if it has inactive products linked
        if self.status == Contract.STATUS_ACTIVE and self.pk:
            inactive_links = (
                Contract_Product.objects
                .filter(contract=self, product__status=Product.STATUS_INACTIVE)
                .select_related("product")
            )
            if inactive_links.exists():
                names = ", ".join(cp.product.designation for cp in inactive_links)
                raise ValidationError(
                    f"Cannot activate this contract: the following linked products are inactive: {names}."
                )


# -----------------------
# 5. Contract ↔ Product
# -----------------------

class Contract_Product(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    external_designation = models.CharField(max_length=255)
    points_per_unit = models.DecimalField(
        max_digits=6, decimal_places=2, default=1,
        help_text="Points multiplier per dirham of PPV. Default 1 = 1 pt/MAD.",
    )
    target_quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "Contract_Product"
        unique_together = [
            ("contract", "product"),
            ("contract", "external_designation"),
        ]

    def clean(self):
        # A contract cannot have two products sharing the same external designation.
        # The unique_together constraint enforces this at DB level; this clean()
        # surfaces it as a friendly ValidationError on forms and the admin.
        if self.contract_id and self.external_designation:
            qs = Contract_Product.objects.filter(
                contract=self.contract,
                external_designation=self.external_designation,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            # Exclude rows being deleted in the same formset submission
            skip_pks = getattr(self, '_skip_unique_pks', None)
            if skip_pks:
                qs = qs.exclude(pk__in=skip_pks)
            if qs.exists():
                raise ValidationError(
                    "This external designation is already used by another product "
                    "in this contract. Each product must have a unique external designation."
                )

    def __str__(self):
        return f"{self.contract} - {self.product}"


# -----------------------
# 6. RoleProfile
# -----------------------

class RoleProfile(TraceableMixin, models.Model):
    """Display metadata (icon) for a Django auth Group (Role)."""
    group = models.OneToOneField(
        'auth.Group',
        on_delete=models.CASCADE,
        related_name='profile',
    )
    icon = models.CharField(max_length=100, default='badge')

    class Meta:
        db_table = 'RoleProfile'

    def __str__(self):
        return self.group.name