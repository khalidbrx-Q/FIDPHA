from rest_framework import serializers
from django.contrib.auth.models import User, Group
from django.db.models import Count, F, FloatField, ExpressionWrapper, Sum
from django.db.models.functions import Round

from fidpha.models import Account, Contract, Contract_Product, Product
from api.models import APIToken
from sales.models import Sale


# ---------------------------------------------------------------------------
# Portal — flat serializers
# ---------------------------------------------------------------------------

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "code", "name", "city", "location", "phone", "email", "status"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]


# ---------------------------------------------------------------------------
# Portal — annotation-dependent serializers
# Views must set the listed attributes on each instance before serializing.
# ---------------------------------------------------------------------------

class ContractProductSerializer(serializers.ModelSerializer):
    """
    Requires units_sold, accepted_units, points attributes on each instance.
    Set by views via aggregation dicts before calling this serializer.
    """
    designation    = serializers.CharField(source="product.designation", read_only=True)
    product_status = serializers.CharField(source="product.status", read_only=True)
    units_sold     = serializers.SerializerMethodField()
    accepted_units = serializers.SerializerMethodField()
    points         = serializers.SerializerMethodField()

    def get_units_sold(self, obj):
        return getattr(obj, "units_sold", 0)

    def get_accepted_units(self, obj):
        return getattr(obj, "accepted_units", 0)

    def get_points(self, obj):
        return getattr(obj, "points", 0)

    class Meta:
        model = Contract_Product
        fields = [
            "id", "external_designation", "points_per_unit",
            "designation", "product_status",
            "units_sold", "accepted_units", "points",
        ]


class ContractListItemSerializer(serializers.ModelSerializer):
    """
    Requires total_points, total_units, product_count attributes on each instance.
    """
    total_points  = serializers.SerializerMethodField()
    total_units   = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    def get_total_points(self, obj):
        return getattr(obj, "total_points", 0)

    def get_total_units(self, obj):
        return getattr(obj, "total_units", 0)

    def get_product_count(self, obj):
        return getattr(obj, "product_count", 0)

    class Meta:
        model = Contract
        fields = ["id", "title", "start_date", "end_date", "status",
                  "total_points", "total_units", "product_count"]


class SaleSerializer(serializers.ModelSerializer):
    """
    Requires pts annotation (from get_account_points_queryset or inline annotation).
    Returns None for points when pts is not annotated or product_ppv is null.
    """
    contract_id          = serializers.IntegerField(source="contract_product.contract_id", read_only=True)
    contract_title       = serializers.CharField(source="contract_product.contract.title", read_only=True)
    product_designation  = serializers.CharField(source="contract_product.product.designation", read_only=True)
    external_designation = serializers.CharField(source="contract_product.external_designation", read_only=True)
    points               = serializers.SerializerMethodField()

    def get_points(self, obj):
        val = getattr(obj, "pts", None)
        if val is None:
            return None
        return int(val or 0)

    class Meta:
        model = Sale
        fields = [
            "id", "sale_datetime", "quantity", "ppv", "product_ppv",
            "status", "rejection_reason", "auto_reviewed", "reviewed_at",
            "contract_id", "contract_title",
            "product_designation", "external_designation", "points",
        ]


# ---------------------------------------------------------------------------
# Staff — list serializers (compact)
# ---------------------------------------------------------------------------

class StaffAccountListSerializer(serializers.ModelSerializer):
    contract_count = serializers.SerializerMethodField()
    user_count     = serializers.SerializerMethodField()

    def get_contract_count(self, obj):
        return getattr(obj, "contract_count", 0)

    def get_user_count(self, obj):
        return getattr(obj, "user_count", 0)

    class Meta:
        model = Account
        fields = ["id", "code", "name", "city", "status", "contract_count", "user_count"]


class StaffContractListSerializer(serializers.ModelSerializer):
    account_id    = serializers.IntegerField(source="account.pk", read_only=True)
    account_name  = serializers.CharField(source="account.name", read_only=True)
    product_count = serializers.SerializerMethodField()

    def get_product_count(self, obj):
        return getattr(obj, "product_count", 0)

    class Meta:
        model = Contract
        fields = ["id", "title", "account_id", "account_name",
                  "start_date", "end_date", "status", "product_count"]


class StaffProductSerializer(serializers.ModelSerializer):
    contract_count = serializers.SerializerMethodField()

    def get_contract_count(self, obj):
        return getattr(obj, "contract_count", 0)

    class Meta:
        model = Product
        fields = ["id", "code", "designation", "ppv", "status", "contract_count"]


class StaffUserSerializer(serializers.ModelSerializer):
    groups          = serializers.SerializerMethodField()
    account_id      = serializers.SerializerMethodField()
    account_name    = serializers.SerializerMethodField()
    pharmacy_portal = serializers.SerializerMethodField()

    def get_groups(self, obj):
        return [{"id": g.pk, "name": g.name} for g in obj.groups.all()]

    def get_account_id(self, obj):
        try:
            return obj.profile.account_id
        except Exception:
            return None

    def get_account_name(self, obj):
        try:
            return obj.profile.account.name
        except Exception:
            return None

    def get_pharmacy_portal(self, obj):
        try:
            return obj.profile.account.pharmacy_portal
        except Exception:
            return False

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "is_staff", "is_active", "is_superuser",
            "groups", "account_id", "account_name", "pharmacy_portal",
        ]


class StaffRoleSerializer(serializers.ModelSerializer):
    icon             = serializers.SerializerMethodField()
    permission_count = serializers.SerializerMethodField()
    user_count       = serializers.SerializerMethodField()

    def get_icon(self, obj):
        try:
            return obj.profile.icon
        except Exception:
            return "badge"

    def get_permission_count(self, obj):
        return getattr(obj, "permission_count", 0)

    def get_user_count(self, obj):
        return getattr(obj, "user_count", 0)

    class Meta:
        model = Group
        fields = ["id", "name", "icon", "permission_count", "user_count"]


class StaffAPITokenListSerializer(serializers.ModelSerializer):
    masked_token        = serializers.CharField(read_only=True)
    created_by_username = serializers.SerializerMethodField()

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None

    class Meta:
        model = APIToken
        fields = [
            "id", "name", "masked_token", "is_active",
            "created_at", "last_used_at", "usage_count", "created_by_username",
        ]


# ---------------------------------------------------------------------------
# Staff — detail serializers (full)
# ---------------------------------------------------------------------------

class StaffAccountDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id", "code", "name", "city", "location", "phone", "email",
            "status", "pharmacy_portal", "auto_review_enabled",
        ]


class StaffContractDetailSerializer(serializers.ModelSerializer):
    account_id   = serializers.IntegerField(source="account.pk", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    duration     = serializers.CharField(read_only=True)
    products     = serializers.SerializerMethodField()

    def get_products(self, contract):
        pts_agg = {
            r["contract_product_id"]: int(r["total_pts"] or 0)
            for r in Sale.objects.filter(
                contract_product__contract=contract,
                status=Sale.STATUS_ACCEPTED,
                product_ppv__isnull=False,
            ).annotate(pts=Round(ExpressionWrapper(
                F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
                output_field=FloatField(),
            ))).values("contract_product_id").annotate(total_pts=Sum("pts"))
        }
        units_agg = {
            r["contract_product_id"]: int(r["total"] or 0)
            for r in Sale.objects.filter(
                contract_product__contract=contract,
            ).values("contract_product_id").annotate(total=Sum("quantity"))
        }
        accepted_units_agg = {
            r["contract_product_id"]: int(r["total"] or 0)
            for r in Sale.objects.filter(
                contract_product__contract=contract,
                status=Sale.STATUS_ACCEPTED,
            ).values("contract_product_id").annotate(total=Sum("quantity"))
        }
        cps = (
            Contract_Product.objects
            .filter(contract=contract)
            .select_related("product")
            .order_by("product__designation")
        )
        result = []
        for cp in cps:
            cp.units_sold     = units_agg.get(cp.pk, 0)
            cp.accepted_units = accepted_units_agg.get(cp.pk, 0)
            cp.points         = pts_agg.get(cp.pk, 0)
            result.append(ContractProductSerializer(cp).data)
        return result

    class Meta:
        model = Contract
        fields = [
            "id", "title", "designation", "account_id", "account_name",
            "start_date", "end_date", "status",
            "last_sync_at", "last_sale_datetime", "duration", "products",
        ]


class StaffSaleReviewSerializer(serializers.ModelSerializer):
    batch_id             = serializers.CharField(source="sale_import.batch_id", read_only=True)
    product_designation  = serializers.CharField(source="contract_product.product.designation", read_only=True)
    external_designation = serializers.CharField(source="contract_product.external_designation", read_only=True)
    contract_id          = serializers.IntegerField(source="contract_product.contract_id", read_only=True)
    points               = serializers.SerializerMethodField()
    ppv_mismatch         = serializers.SerializerMethodField()

    def get_points(self, obj):
        val = getattr(obj, "pts", None)
        if val is None:
            return None
        return int(val or 0)

    def get_ppv_mismatch(self, obj):
        if obj.ppv is None or obj.product_ppv is None:
            return False
        return obj.ppv != obj.product_ppv

    class Meta:
        model = Sale
        fields = [
            "id", "sale_datetime", "quantity", "ppv", "product_ppv",
            "status", "rejection_reason", "auto_reviewed", "reviewed_at",
            "batch_id", "product_designation", "external_designation",
            "contract_id", "points", "ppv_mismatch",
        ]


class StaffSaleBatchSerializer(serializers.Serializer):
    """Plain serializer for aggregated batch dicts (not model instances)."""
    batch_id        = serializers.CharField()
    account_code    = serializers.CharField()
    account_name    = serializers.CharField()
    account_pk      = serializers.IntegerField(allow_null=True)
    contract_pk     = serializers.IntegerField(allow_null=True)
    contract_title  = serializers.CharField(allow_null=True)
    received_at_iso = serializers.CharField(allow_null=True)
    total           = serializers.IntegerField()
    pending         = serializers.IntegerField()
    accepted        = serializers.IntegerField()
    rejected        = serializers.IntegerField()
    ppv_mismatch    = serializers.IntegerField()
    sale_date_min   = serializers.CharField(allow_null=True)
    sale_date_max   = serializers.CharField(allow_null=True)
    rejection_rate  = serializers.IntegerField()
