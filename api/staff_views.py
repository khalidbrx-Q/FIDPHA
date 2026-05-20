import datetime
from django.db.models import Count, F, FloatField, ExpressionWrapper, Min, Max, Q, Sum
from django.db.models.functions import Round, TruncDay, TruncHour, TruncMonth, TruncYear
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from django.contrib.auth.models import User, Group, Permission
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.contenttypes.models import ContentType
from django.db.models.deletion import ProtectedError

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from fidpha.models import Account, Contract, Contract_Product, Product, RoleProfile, UserProfile
from api.models import APIToken, APITokenUsageLog
from sales.models import Sale, SaleImport
from control.models import SystemConfig

from api.permissions import StaffSessionPermission
from api.serializers import (
    StaffAccountListSerializer,
    StaffAccountDetailSerializer,
    StaffContractListSerializer,
    StaffContractDetailSerializer,
    StaffProductSerializer,
    StaffUserSerializer,
    StaffRoleSerializer,
    StaffAPITokenListSerializer,
    StaffSaleReviewSerializer,
    StaffSaleBatchSerializer,
)

_AUTH  = [SessionAuthentication]
_PERMS = [StaffSessionPermission]


def _require_perm(request, perm):
    if not request.user.has_perm(perm):
        raise PermissionDenied()


def _require_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied()


def _log(user, obj, flag, message=""):
    LogEntry.objects.log_action(
        user_id=user.pk,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=obj.pk,
        object_repr=str(obj)[:200],
        action_flag=flag,
        change_message=message,
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class StaffDashboardStatsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        return Response({
            "accounts_active":  Account.objects.filter(status=Account.STATUS_ACTIVE).count(),
            "accounts_total":   Account.objects.count(),
            "contracts_active": Contract.objects.filter(status=Contract.STATUS_ACTIVE).count(),
            "contracts_total":  Contract.objects.count(),
            "products_active":  Product.objects.filter(status=Product.STATUS_ACTIVE).count(),
            "products_total":   Product.objects.count(),
            "users_total":      User.objects.count(),
            "tokens_active":    APIToken.objects.filter(is_active=True).count(),
            "tokens_total":     APIToken.objects.count(),
        })


class StaffDashboardActivityView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        entries = (
            LogEntry.objects
            .select_related("user", "content_type")
            .exclude(change_message__startswith="[")
            .order_by("-action_time")[:25]
        )
        items = [
            {
                "action":       entry.action_flag,
                "object_repr":  entry.object_repr,
                "content_type": entry.content_type.model if entry.content_type else "",
                "timestamp":    entry.action_time.isoformat(),
                "user":         entry.user.username if entry.user else "",
            }
            for entry in entries
        ]
        return Response({"items": items, "ADDITION": ADDITION, "CHANGE": CHANGE, "DELETION": DELETION})


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

class StaffAccountsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "fidpha.view_account")
        qs = (
            Account.objects
            .annotate(
                contract_count=Count("contracts", distinct=True),
                user_count=Count("users", distinct=True),
            )
            .order_by("name")
        )
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(city__icontains=q))
        status_f = request.GET.get("status", "").strip()
        if status_f in (Account.STATUS_ACTIVE, Account.STATUS_INACTIVE):
            qs = qs.filter(status=status_f)

        paginator = Paginator(qs, 25)
        page      = paginator.get_page(request.GET.get("page", 1))
        return Response({
            "items":    StaffAccountListSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })

    def post(self, request):
        _require_perm(request, "fidpha.add_account")
        data    = request.data
        account = Account(
            code               = data.get("code", "").strip(),
            name               = data.get("name", "").strip(),
            city               = data.get("city", "").strip(),
            location           = data.get("location", "").strip(),
            phone              = data.get("phone", "").strip(),
            email              = data.get("email", "").strip(),
            status             = data.get("status", Account.STATUS_ACTIVE),
            pharmacy_portal    = bool(data.get("pharmacy_portal", False)),
            auto_review_enabled = bool(data.get("auto_review_enabled", False)),
            created_by         = request.user,
            modified_by        = request.user,
        )
        try:
            account.full_clean()
        except Exception as e:
            raise ValidationError(str(e))
        account.save()
        _log(request.user, account, ADDITION)
        return Response(StaffAccountDetailSerializer(account).data, status=201)


class StaffAccountDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "fidpha.view_account")
        account = get_object_or_404(Account, pk=pk)
        return Response(StaffAccountDetailSerializer(account).data)

    def patch(self, request, pk):
        _require_perm(request, "fidpha.change_account")
        account = get_object_or_404(Account, pk=pk)
        data    = request.data
        fields  = ["name", "city", "location", "phone", "email", "status",
                   "pharmacy_portal", "auto_review_enabled"]
        for f in fields:
            if f in data:
                setattr(account, f, data[f])
        account.modified_by = request.user
        try:
            account.full_clean()
        except Exception as e:
            raise ValidationError(str(e))
        account.save()
        _log(request.user, account, CHANGE)
        return Response(StaffAccountDetailSerializer(account).data)

    def delete(self, request, pk):
        _require_perm(request, "fidpha.delete_account")
        account = get_object_or_404(Account, pk=pk)
        try:
            _log(request.user, account, DELETION)
            account.delete()
        except ProtectedError as e:
            return Response({"detail": "Cannot delete: account has related records."}, status=409)
        return Response(status=204)


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

class StaffContractsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "fidpha.view_contract")
        qs = (
            Contract.objects
            .select_related("account")
            .annotate(product_count=Count("contract_product", distinct=True))
            .order_by("-status", "-start_date")
        )
        account_pk = request.GET.get("account", "").strip()
        status_f   = request.GET.get("status", "").strip()
        q          = request.GET.get("q", "").strip()
        if account_pk:
            qs = qs.filter(account_id=account_pk)
        if status_f in (Contract.STATUS_ACTIVE, Contract.STATUS_INACTIVE):
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(title__icontains=q)

        paginator = Paginator(qs, 25)
        page      = paginator.get_page(request.GET.get("page", 1))
        return Response({
            "items":    StaffContractListSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })

    def post(self, request):
        _require_perm(request, "fidpha.add_contract")
        data     = request.data
        account  = get_object_or_404(Account, pk=data.get("account_id"))
        start_dt = parse_datetime(str(data.get("start_date", "")))
        end_dt   = parse_datetime(str(data.get("end_date", "")))
        if not start_dt or not end_dt:
            raise ValidationError("start_date and end_date are required ISO datetime strings.")
        contract = Contract(
            title       = data.get("title", "").strip(),
            designation = data.get("designation", "").strip(),
            start_date  = start_dt,
            end_date    = end_dt,
            account     = account,
            status      = data.get("status", Contract.STATUS_INACTIVE),
            created_by  = request.user,
            modified_by = request.user,
        )
        try:
            contract.full_clean()
        except Exception as e:
            raise ValidationError(str(e))
        contract.save()
        _log(request.user, contract, ADDITION)
        return Response(StaffContractDetailSerializer(contract).data, status=201)


class StaffContractDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "fidpha.view_contract")
        contract = get_object_or_404(Contract.objects.select_related("account"), pk=pk)
        return Response(StaffContractDetailSerializer(contract).data)

    def patch(self, request, pk):
        _require_perm(request, "fidpha.change_contract")
        contract = get_object_or_404(Contract.objects.select_related("account"), pk=pk)
        data     = request.data
        if "title" in data:
            contract.title = data["title"]
        if "designation" in data:
            contract.designation = data["designation"]
        if "status" in data:
            contract.status = data["status"]
        if "start_date" in data:
            dt = parse_datetime(str(data["start_date"]))
            if dt:
                contract.start_date = dt
        if "end_date" in data:
            dt = parse_datetime(str(data["end_date"]))
            if dt:
                contract.end_date = dt
        contract.modified_by = request.user
        try:
            contract.full_clean()
        except Exception as e:
            raise ValidationError(str(e))
        contract.save()
        _log(request.user, contract, CHANGE)
        return Response(StaffContractDetailSerializer(contract).data)

    def delete(self, request, pk):
        _require_perm(request, "fidpha.delete_contract")
        contract = get_object_or_404(Contract, pk=pk)
        try:
            _log(request.user, contract, DELETION)
            contract.delete()
        except ProtectedError:
            return Response({"detail": "Cannot delete: contract has sales records."}, status=409)
        return Response(status=204)


class StaffContractChartsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "fidpha.view_contract")
        contract = get_object_or_404(Contract.objects.select_related("account"), pk=pk)

        def _pts_qs():
            return Sale.objects.filter(
                contract_product__contract=contract,
                status=Sale.STATUS_ACCEPTED,
                product_ppv__isnull=False,
            ).annotate(pts=Round(ExpressionWrapper(
                F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
                output_field=FloatField(),
            )))

        year_rows = (
            _pts_qs().annotate(yr=TruncYear("sale_datetime"))
            .values_list("yr", flat=True).distinct().order_by("yr")
        )
        available_years = sorted({dt.year for dt in year_rows if dt})

        years_monthly = {}
        for yr in available_years:
            yr_months = [datetime.datetime(yr, m, 1, tzinfo=datetime.timezone.utc) for m in range(1, 13)]
            yr_mqs    = (
                _pts_qs().filter(sale_datetime__year=yr)
                .annotate(month=TruncMonth("sale_datetime"))
                .values("month")
                .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
            )
            mmap = {r["month"].strftime("%Y-%m"): r for r in yr_mqs}
            years_monthly[str(yr)] = {
                "keys":   [d.strftime("%Y-%m") for d in yr_months],
                "labels": [d.strftime("%b") for d in yr_months],
                "pts":    [int(mmap.get(d.strftime("%Y-%m"), {}).get("total") or 0) for d in yr_months],
                "prods":  [mmap.get(d.strftime("%Y-%m"), {}).get("unique_products") or 0 for d in yr_months],
            }

        cp_pts_agg = {
            r["contract_product_id"]: int(r["total_pts"] or 0)
            for r in _pts_qs().values("contract_product_id").annotate(total_pts=Sum("pts"))
        }
        cp_units_agg = {
            r["contract_product_id"]: int(r["total"] or 0)
            for r in Sale.objects.filter(
                contract_product__contract=contract,
                status=Sale.STATUS_ACCEPTED,
            ).values("contract_product_id").annotate(total=Sum("quantity"))
        }
        cps = (
            Contract_Product.objects.filter(contract=contract)
            .select_related("product").order_by("product__designation")
        )
        products_data = [
            {
                "designation": cp.product.designation,
                "units_sold":  cp_units_agg.get(cp.pk, 0),
                "points":      cp_pts_agg.get(cp.pk, 0),
            }
            for cp in cps
        ]

        return Response({
            "available_years": available_years,
            "years_monthly":   years_monthly,
            "products_data":   products_data,
        })


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class StaffProductsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "fidpha.view_product")
        qs = (
            Product.objects
            .annotate(contract_count=Count("contracts", distinct=True))
            .order_by("designation")
        )
        q        = request.GET.get("q", "").strip()
        status_f = request.GET.get("status", "").strip()
        if q:
            qs = qs.filter(Q(designation__icontains=q) | Q(code__icontains=q))
        if status_f in (Product.STATUS_ACTIVE, Product.STATUS_INACTIVE):
            qs = qs.filter(status=status_f)

        paginator = Paginator(qs, 25)
        page      = paginator.get_page(request.GET.get("page", 1))
        return Response({
            "items":    StaffProductSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })

    def post(self, request):
        _require_perm(request, "fidpha.add_product")
        data    = request.data
        product = Product(
            code        = data.get("code", "").strip(),
            designation = data.get("designation", "").strip(),
            ppv         = data.get("ppv"),
            status      = data.get("status", Product.STATUS_ACTIVE),
            created_by  = request.user,
            modified_by = request.user,
        )
        try:
            product.full_clean()
        except Exception as e:
            raise ValidationError(str(e))
        product.save()
        _log(request.user, product, ADDITION)
        return Response(StaffProductSerializer(product).data, status=201)


class StaffProductDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "fidpha.view_product")
        product = get_object_or_404(
            Product.objects.annotate(contract_count=Count("contracts", distinct=True)),
            pk=pk,
        )
        return Response(StaffProductSerializer(product).data)

    def patch(self, request, pk):
        _require_perm(request, "fidpha.change_product")
        product = get_object_or_404(Product, pk=pk)
        data    = request.data
        for f in ["designation", "ppv", "status"]:
            if f in data:
                setattr(product, f, data[f])
        product.modified_by = request.user
        try:
            product.full_clean()
        except Exception as e:
            raise ValidationError(str(e))
        product.save()
        _log(request.user, product, CHANGE)
        return Response(StaffProductSerializer(
            Product.objects.annotate(contract_count=Count("contracts", distinct=True)).get(pk=product.pk)
        ).data)

    def delete(self, request, pk):
        _require_perm(request, "fidpha.delete_product")
        product = get_object_or_404(Product, pk=pk)
        try:
            _log(request.user, product, DELETION)
            product.delete()
        except ProtectedError:
            return Response({"detail": "Cannot delete: product is linked to contracts."}, status=409)
        return Response(status=204)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class StaffUsersView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "auth.view_user")
        qs = User.objects.prefetch_related("groups").order_by("username")
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(email__icontains=q) |
                Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )
        paginator = Paginator(qs, 25)
        page      = paginator.get_page(request.GET.get("page", 1))
        return Response({
            "items":    StaffUserSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })

    def post(self, request):
        _require_perm(request, "auth.add_user")
        data = request.data
        if not data.get("username") or not data.get("password"):
            raise ValidationError("username and password are required.")
        if User.objects.filter(username=data["username"]).exists():
            raise ValidationError("Username already exists.")
        user = User.objects.create_user(
            username   = data["username"].strip(),
            email      = data.get("email", "").strip(),
            password   = data["password"],
            first_name = data.get("first_name", "").strip(),
            last_name  = data.get("last_name", "").strip(),
            is_staff   = bool(data.get("is_staff", False)),
            is_active  = bool(data.get("is_active", True)),
        )
        if "groups" in data:
            user.groups.set(Group.objects.filter(pk__in=data["groups"]))
        _log(request.user, user, ADDITION)
        return Response(StaffUserSerializer(user).data, status=201)


class StaffUserDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "auth.view_user")
        user = get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)
        return Response(StaffUserSerializer(user).data)

    def patch(self, request, pk):
        _require_perm(request, "auth.change_user")
        user = get_object_or_404(User, pk=pk)
        data = request.data
        for f in ["first_name", "last_name", "email", "is_active"]:
            if f in data:
                setattr(user, f, data[f])
        if "groups" in data:
            user.groups.set(Group.objects.filter(pk__in=data["groups"]))
        if "password" in data and data["password"]:
            user.set_password(data["password"])
        user.save()
        _log(request.user, user, CHANGE)
        return Response(StaffUserSerializer(User.objects.prefetch_related("groups").get(pk=user.pk)).data)

    def delete(self, request, pk):
        _require_perm(request, "auth.delete_user")
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            return Response({"detail": "Cannot delete your own account."}, status=400)
        try:
            _log(request.user, user, DELETION)
            user.delete()
        except ProtectedError:
            return Response({"detail": "Cannot delete: user has related records."}, status=409)
        return Response(status=204)


# ---------------------------------------------------------------------------
# Roles (Groups)
# ---------------------------------------------------------------------------

class StaffRolesView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "auth.view_group")
        qs = (
            Group.objects
            .annotate(
                permission_count=Count("permissions", distinct=True),
                user_count=Count("user", distinct=True),
            )
            .prefetch_related("profile")
            .order_by("name")
        )
        return Response({"items": StaffRoleSerializer(qs, many=True).data})

    def post(self, request):
        _require_perm(request, "auth.add_group")
        data = request.data
        if not data.get("name"):
            raise ValidationError("name is required.")
        group = Group.objects.create(name=data["name"])
        if "permissions" in data:
            group.permissions.set(Permission.objects.filter(pk__in=data["permissions"]))
        icon = data.get("icon", "badge")
        RoleProfile.objects.update_or_create(group=group, defaults={"icon": icon, "created_by": request.user, "modified_by": request.user})
        _log(request.user, group, ADDITION)
        group.permission_count = group.permissions.count()
        group.user_count       = 0
        return Response(StaffRoleSerializer(group).data, status=201)


class StaffRoleDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "auth.view_group")
        group = get_object_or_404(
            Group.objects.annotate(
                permission_count=Count("permissions", distinct=True),
                user_count=Count("user", distinct=True),
            ).prefetch_related("profile"),
            pk=pk,
        )
        return Response(StaffRoleSerializer(group).data)

    def patch(self, request, pk):
        _require_perm(request, "auth.change_group")
        group = get_object_or_404(Group, pk=pk)
        data  = request.data
        if "name" in data:
            group.name = data["name"]
            group.save()
        if "permissions" in data:
            group.permissions.set(Permission.objects.filter(pk__in=data["permissions"]))
        if "icon" in data:
            RoleProfile.objects.update_or_create(
                group=group,
                defaults={"icon": data["icon"], "modified_by": request.user},
            )
        _log(request.user, group, CHANGE)
        group = Group.objects.annotate(
            permission_count=Count("permissions", distinct=True),
            user_count=Count("user", distinct=True),
        ).get(pk=group.pk)
        return Response(StaffRoleSerializer(group).data)

    def delete(self, request, pk):
        _require_perm(request, "auth.delete_group")
        group = get_object_or_404(Group, pk=pk)
        try:
            _log(request.user, group, DELETION)
            group.delete()
        except ProtectedError:
            return Response({"detail": "Cannot delete: group has related records."}, status=409)
        return Response(status=204)


# ---------------------------------------------------------------------------
# API Tokens
# ---------------------------------------------------------------------------

class StaffTokensView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "api.view_apitoken")
        qs       = APIToken.objects.select_related("created_by").order_by("-created_at")
        active_f = request.GET.get("active", "").strip()
        if active_f == "1":
            qs = qs.filter(is_active=True)
        elif active_f == "0":
            qs = qs.filter(is_active=False)

        paginator = Paginator(qs, 25)
        page      = paginator.get_page(request.GET.get("page", 1))
        return Response({
            "items":    StaffAPITokenListSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })

    def post(self, request):
        _require_perm(request, "api.add_apitoken")
        name = request.data.get("name", "").strip()
        if not name:
            raise ValidationError("name is required.")
        token            = APIToken(name=name, created_by=request.user)
        token.save()
        raw              = token.raw_token
        _log(request.user, token, ADDITION)
        data             = StaffAPITokenListSerializer(token).data
        data["raw_token"] = raw
        return Response(data, status=201)


class StaffTokenDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        _require_perm(request, "api.view_apitoken")
        token = get_object_or_404(APIToken.objects.select_related("created_by"), pk=pk)

        now      = timezone.now()
        days_30  = [now.date() - datetime.timedelta(days=i) for i in range(29, -1, -1)]
        days_7   = [now.date() - datetime.timedelta(days=i) for i in range(6, -1, -1)]

        counts_30 = {
            row["day"].date(): row["count"]
            for row in APITokenUsageLog.objects.filter(
                token=token,
                called_at__date__gte=days_30[0],
            ).annotate(day=TruncDay("called_at")).values("day").annotate(count=Count("id"))
        }
        counts_7 = {
            row["day"].date(): row["count"]
            for row in APITokenUsageLog.objects.filter(
                token=token,
                called_at__date__gte=days_7[0],
            ).annotate(day=TruncDay("called_at")).values("day").annotate(count=Count("id"))
        }
        counts_today = {
            row["hr"].hour: row["count"]
            for row in APITokenUsageLog.objects.filter(
                token=token,
                called_at__date=now.date(),
            ).annotate(hr=TruncHour("called_at")).values("hr").annotate(count=Count("id"))
            if row["hr"]
        }

        data = StaffAPITokenListSerializer(token).data
        data.update({
            "chart_30_labels":    [d.strftime("%d %b") for d in days_30],
            "chart_30_data":      [counts_30.get(d, 0) for d in days_30],
            "chart_7_labels":     [d.strftime("%a %d") for d in days_7],
            "chart_7_data":       [counts_7.get(d, 0) for d in days_7],
            "chart_today_labels": [f"{h:02d}:00" for h in range(24)],
            "chart_today_data":   [counts_today.get(h, 0) for h in range(24)],
            "total_today":        sum(counts_today.values()),
        })
        return Response(data)

    def delete(self, request, pk):
        _require_perm(request, "api.delete_apitoken")
        token = get_object_or_404(APIToken, pk=pk)
        _log(request.user, token, DELETION)
        token.delete()
        return Response(status=204)


class StaffTokenRevokeView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def post(self, request, pk):
        _require_perm(request, "api.change_apitoken")
        token           = get_object_or_404(APIToken, pk=pk)
        token.is_active = False
        token.save(update_fields=["is_active"])
        _log(request.user, token, CHANGE, "Revoked")
        return Response(StaffAPITokenListSerializer(token).data)


class StaffTokenReactivateView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def post(self, request, pk):
        _require_perm(request, "api.change_apitoken")
        token           = get_object_or_404(APIToken, pk=pk)
        token.is_active = True
        token.save(update_fields=["is_active"])
        _log(request.user, token, CHANGE, "Reactivated")
        return Response(StaffAPITokenListSerializer(token).data)


# ---------------------------------------------------------------------------
# Sales Review
# ---------------------------------------------------------------------------

class StaffSaleBatchesView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "sales.view_sale")

        date_from   = request.GET.get("date_from",  "").strip()
        date_to     = request.GET.get("date_to",    "").strip()
        account_pk  = request.GET.get("account",    "").strip()
        contract_pk = request.GET.get("contract",   "").strip()
        status_f    = request.GET.get("status",     "").strip()
        batch_q     = request.GET.get("q",          "").strip()
        try:
            page     = max(1, int(request.GET.get("page", 1)))
        except ValueError:
            page     = 1
        per_page = 25

        qs = Sale.objects.values("sale_import__batch_id", "sale_import__account_code")

        if date_from:
            qs = qs.filter(sale_import__received_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(sale_import__received_at__date__lte=date_to)
        if account_pk:
            try:
                acc = Account.objects.get(pk=account_pk)
                qs  = qs.filter(sale_import__account_code=acc.code)
            except Account.DoesNotExist:
                pass
        if contract_pk:
            qs = qs.filter(contract_product__contract_id=contract_pk)
        if batch_q:
            qs = qs.filter(sale_import__batch_id__icontains=batch_q)

        qs = qs.annotate(
            received_at   = Min("sale_import__received_at"),
            total         = Count("pk"),
            pending       = Count("pk", filter=Q(status=Sale.STATUS_PENDING)),
            accepted      = Count("pk", filter=Q(status=Sale.STATUS_ACCEPTED)),
            rejected      = Count("pk", filter=Q(status=Sale.STATUS_REJECTED)),
            ppv_mismatch  = Count(
                "pk",
                filter=Q(contract_product__product__ppv__isnull=False)
                       & ~Q(ppv=F("contract_product__product__ppv")),
            ),
            sale_date_min = Min("sale_datetime"),
            sale_date_max = Max("sale_datetime"),
        )

        if status_f == "pending":
            qs = qs.filter(pending__gt=0)
        elif status_f == "accepted":
            qs = qs.filter(accepted__gt=0)
        elif status_f == "rejected":
            qs = qs.filter(rejected__gt=0)

        qs          = qs.order_by("-received_at", "sale_import__batch_id")
        total_count = qs.count()
        offset      = (page - 1) * per_page
        page_rows   = list(qs[offset: offset + per_page])

        account_codes = {b["sale_import__account_code"] for b in page_rows}
        batch_ids     = {b["sale_import__batch_id"]     for b in page_rows}

        account_map = {
            a.code: {"name": a.name, "pk": a.pk}
            for a in Account.objects.filter(code__in=account_codes)
        }
        contract_map = {}
        if batch_ids:
            for row in (
                Sale.objects
                .filter(sale_import__batch_id__in=batch_ids)
                .values("sale_import__batch_id", "contract_product__contract_id",
                        "contract_product__contract__title")
                .distinct()
            ):
                bid = row["sale_import__batch_id"]
                if bid not in contract_map:
                    contract_map[bid] = {
                        "pk":    row["contract_product__contract_id"],
                        "title": row["contract_product__contract__title"],
                    }

        batches = []
        for b in page_rows:
            acc = account_map.get(b["sale_import__account_code"], {})
            ct  = contract_map.get(b["sale_import__batch_id"], {})
            batches.append({
                "batch_id":       b["sale_import__batch_id"],
                "account_code":   b["sale_import__account_code"],
                "account_name":   acc.get("name", b["sale_import__account_code"]),
                "account_pk":     acc.get("pk"),
                "contract_pk":    ct.get("pk"),
                "contract_title": ct.get("title"),
                "received_at_iso": b["received_at"].isoformat() if b["received_at"] else None,
                "total":          b["total"],
                "pending":        b["pending"],
                "accepted":       b["accepted"],
                "rejected":       b["rejected"],
                "ppv_mismatch":   b["ppv_mismatch"],
                "sale_date_min":  b["sale_date_min"].strftime("%Y-%m-%dT%H:%M:%S") if b["sale_date_min"] else None,
                "sale_date_max":  b["sale_date_max"].strftime("%Y-%m-%dT%H:%M:%S") if b["sale_date_max"] else None,
                "rejection_rate": (
                    round(b["rejected"] * 100 / (b["accepted"] + b["rejected"]))
                    if (b["accepted"] + b["rejected"]) > 0 else -1
                ),
            })

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        return Response({
            "batches":  batches,
            "total":    total_count,
            "page":     page,
            "pages":    total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        })


class StaffSalesView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_perm(request, "sales.view_sale")
        contract_pk = request.GET.get("contract", "").strip()
        batch_id    = request.GET.get("batch",    "").strip()

        qs = Sale.objects.select_related(
            "contract_product__product",
            "contract_product__contract",
            "sale_import",
        ).annotate(pts=Round(ExpressionWrapper(
            F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
            output_field=FloatField(),
        ))).order_by("-sale_datetime")

        if contract_pk:
            qs = qs.filter(contract_product__contract_id=contract_pk)
        if batch_id:
            qs = qs.filter(sale_import__batch_id=batch_id)

        status_f = request.GET.get("status", "").strip()
        if status_f in (Sale.STATUS_ACCEPTED, Sale.STATUS_REJECTED, Sale.STATUS_PENDING):
            qs = qs.filter(status=status_f)

        paginator = Paginator(qs, 50)
        page      = paginator.get_page(request.GET.get("page", 1))
        return Response({
            "items":    StaffSaleReviewSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })


class StaffSaleAcceptView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def post(self, request, pk):
        _require_perm(request, "sales.change_sale")
        sale             = get_object_or_404(Sale, pk=pk)
        sale.status      = Sale.STATUS_ACCEPTED
        sale.reviewed_by = request.user
        sale.reviewed_at = timezone.now()
        sale.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        return Response(StaffSaleReviewSerializer(sale).data)


class StaffSaleRejectView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def post(self, request, pk):
        _require_perm(request, "sales.change_sale")
        sale                  = get_object_or_404(Sale, pk=pk)
        sale.status           = Sale.STATUS_REJECTED
        sale.rejection_reason = request.data.get("rejection_reason", "")
        sale.reviewed_by      = request.user
        sale.reviewed_at      = timezone.now()
        sale.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])
        return Response(StaffSaleReviewSerializer(sale).data)


class StaffSalesBulkUpdateView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def post(self, request):
        _require_perm(request, "sales.change_sale")
        ids              = request.data.get("ids", [])
        new_status       = request.data.get("status", "").strip()
        rejection_reason = request.data.get("rejection_reason", "")

        if not ids or not isinstance(ids, list):
            raise ValidationError("ids must be a non-empty list.")
        if new_status not in (Sale.STATUS_ACCEPTED, Sale.STATUS_REJECTED, Sale.STATUS_PENDING):
            raise ValidationError("status must be accepted, rejected, or pending.")

        update_fields = {
            "status":      new_status,
            "reviewed_by": request.user,
            "reviewed_at": timezone.now(),
        }
        if new_status == Sale.STATUS_REJECTED:
            update_fields["rejection_reason"] = rejection_reason

        updated = Sale.objects.filter(pk__in=ids).update(**update_fields)
        return Response({"updated": updated})


# ---------------------------------------------------------------------------
# Sync Log (superuser only)
# ---------------------------------------------------------------------------

class StaffSyncLogView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_superuser(request)

        qs = SaleImport.objects.order_by("-received_at")

        status_f  = request.GET.get("status",  "").strip()
        batch_q   = request.GET.get("batch",   "").strip()
        account_q = request.GET.get("account", "").strip()
        date_from = request.GET.get("date_from", "").strip()
        date_to   = request.GET.get("date_to",   "").strip()
        reason_q  = request.GET.get("reason",  "").strip()

        if status_f in (SaleImport.STATUS_PENDING, SaleImport.STATUS_ACCEPTED, SaleImport.STATUS_REJECTED):
            qs = qs.filter(status=status_f)
        if batch_q:
            qs = qs.filter(batch_id__icontains=batch_q)
        if account_q:
            qs = qs.filter(account_code__icontains=account_q)
        if date_from:
            qs = qs.filter(received_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(received_at__date__lte=date_to)
        if reason_q:
            qs = qs.filter(rejection_reason__icontains=reason_q)

        paginator = Paginator(qs, 50)
        page      = paginator.get_page(request.GET.get("page", 1))

        items = [
            {
                "id":                   si.pk,
                "batch_id":             si.batch_id,
                "account_code":         si.account_code,
                "external_designation": si.external_designation,
                "sale_datetime":        si.sale_datetime.isoformat() if si.sale_datetime else None,
                "quantity":             si.quantity,
                "ppv":                  str(si.ppv),
                "status":               si.status,
                "rejection_reason":     si.rejection_reason,
                "received_at":          si.received_at.isoformat() if si.received_at else None,
            }
            for si in page.object_list
        ]
        return Response({
            "items":    items,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })


# ---------------------------------------------------------------------------
# System Settings (superuser only)
# ---------------------------------------------------------------------------

class StaffSystemSettingsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        _require_superuser(request)
        config = SystemConfig.get()
        return Response({
            "auto_review_enabled":    config.auto_review_enabled,
            "auto_review_updated_at": config.auto_review_updated_at.isoformat() if config.auto_review_updated_at else None,
            "auto_review_updated_by": (
                config.auto_review_updated_by.username if config.auto_review_updated_by else None
            ),
        })

    def patch(self, request):
        _require_superuser(request)
        config = SystemConfig.get()
        if "auto_review_enabled" in request.data:
            config.auto_review_enabled    = bool(request.data["auto_review_enabled"])
            config.auto_review_updated_by = request.user
            config.save(update_fields=["auto_review_enabled", "auto_review_updated_by"])
        return Response({
            "auto_review_enabled":    config.auto_review_enabled,
            "auto_review_updated_at": config.auto_review_updated_at.isoformat() if config.auto_review_updated_at else None,
            "auto_review_updated_by": (
                config.auto_review_updated_by.username if config.auto_review_updated_by else None
            ),
        })
