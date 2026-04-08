from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


# -----------------------
# 1. Account (Pharmacie)
# -----------------------

class Account(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    location = models.TextField()
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    pharmacy_portal = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Account"

    def __str__(self):
        return f"[{self.code}] {self.name} - {self.city}"

    def clean(self):
        # Rule 3: cannot deactivate account if it has at least one active contract
        if self.status == "inactive" and self.pk:
            active_contracts = self.contracts.filter(status="active")
            if active_contracts.exists():
                raise ValidationError(
                    "Cannot deactivate this account because it has active contracts. "
                    "Please deactivate all contracts first."
                )


# -----------------------
# 2. UserProfile
# -----------------------

class UserProfile(models.Model):
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

class Product(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Product"

    def __str__(self):
        return self.designation

    def clean(self):
        # Rule 2: cannot deactivate a product if it is in at least one active contract
        if self.status == "inactive" and self.pk:
            active_contracts = Contract_Product.objects.filter(
                product=self,
                contract__status="active"
            )
            if active_contracts.exists():
                raise ValidationError(
                    "Cannot deactivate this product because it is referenced in active contracts. "
                    "Please deactivate those contracts first."
                )


# -----------------------
# 4. Contract
# -----------------------

class Contract(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
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

    class Meta:
        db_table = "Contract"

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
        if self.status == "active" and self.account_id:
            active_contracts = Contract.objects.filter(
                account=self.account,
                status="active"
            )
            if self.pk:
                active_contracts = active_contracts.exclude(pk=self.pk)
            if active_contracts.exists():
                raise ValidationError(
                    "This account already has an active contract. "
                    "Please deactivate it before creating a new one."
                )


# -----------------------
# 5. Contract ↔ Product
# -----------------------

class Contract_Product(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    external_designation = models.CharField(max_length=255)

    class Meta:
        db_table = "Contract_Product"
        unique_together = ("contract", "product")

    def __str__(self):
        return f"{self.contract} - {self.product}"