import calendar as cal
import datetime
from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Count, F, FloatField, ExpressionWrapper, Q, Sum
from django.db.models.functions import Round, TruncDay, TruncMonth, TruncYear
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from fidpha.models import Contract, Contract_Product
from fidpha.services import get_account_points_queryset
from sales.models import Sale, SaleImport

from api.permissions import PortalSessionPermission
from api.serializers import (
    AccountSerializer,
    ContractListItemSerializer,
    ContractProductSerializer,
    SaleSerializer,
    UserSerializer,
)

_AUTH  = [SessionAuthentication]
_PERMS = [PortalSessionPermission]


def _get_account(request):
    try:
        return request.user.profile.account
    except Exception:
        raise PermissionDenied()


def _build_month_dates(n=12):
    now = timezone.now()
    dates = []
    for i in range(n - 1, -1, -1):
        m, y = now.month - i, now.year
        while m <= 0:
            m += 12
            y -= 1
        dates.append(datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc))
    return dates


# ---------------------------------------------------------------------------
# GET /api/portal/account/
# ---------------------------------------------------------------------------

class PortalAccountView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account = _get_account(request)
        return Response({
            "account":        AccountSerializer(account).data,
            "user":           UserSerializer(request.user).data,
            "email_verified": request.user.profile.email_verified,
        })


# ---------------------------------------------------------------------------
# GET /api/portal/dashboard/stats/
# ---------------------------------------------------------------------------

class DashboardStatsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account      = _get_account(request)
        base_qs      = get_account_points_queryset(account)
        now          = timezone.now()
        month_start  = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_points     = int(base_qs.aggregate(t=Sum("pts"))["t"] or 0)
        this_month_pts   = int(base_qs.filter(sale_datetime__gte=month_start).aggregate(t=Sum("pts"))["t"] or 0)
        this_month_units = int(
            Sale.objects.filter(
                contract_product__contract__account=account,
                status=Sale.STATUS_ACCEPTED,
                sale_datetime__gte=month_start,
            ).aggregate(t=Sum("quantity"))["t"] or 0
        )
        products_count  = base_qs.values("contract_product__product").distinct().count()
        contracts_count = account.contracts.count()
        active_contract = account.contracts.filter(status=Contract.STATUS_ACTIVE).first()

        return Response({
            "total_points":      total_points,
            "this_month_points": this_month_pts,
            "this_month_units":  this_month_units,
            "products_count":    products_count,
            "contracts_count":   contracts_count,
            "active_contract": {
                "id":     active_contract.pk,
                "title":  active_contract.title,
                "status": active_contract.status,
            } if active_contract else None,
        })


# ---------------------------------------------------------------------------
# GET /api/portal/dashboard/charts/
# ---------------------------------------------------------------------------

class DashboardChartsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account      = _get_account(request)
        base_qs      = get_account_points_queryset(account)
        now          = timezone.now()
        month_dates  = _build_month_dates(12)

        cumul_base = int(
            base_qs.filter(sale_datetime__lt=month_dates[0]).aggregate(t=Sum("pts"))["t"] or 0
        )

        monthly_qs = (
            base_qs.filter(sale_datetime__gte=month_dates[0])
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month")
            .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
        )
        monthly_map          = {r["month"].strftime("%Y-%m"): int(r["total"] or 0) for r in monthly_qs}
        monthly_products_map = {r["month"].strftime("%Y-%m"): r["unique_products"] for r in monthly_qs}

        units_map = {
            r["month"].strftime("%Y-%m"): int(r["total"] or 0)
            for r in Sale.objects.filter(
                contract_product__contract__account=account,
                status=Sale.STATUS_ACCEPTED,
                sale_datetime__gte=month_dates[0],
            ).annotate(month=TruncMonth("sale_datetime")).values("month").annotate(total=Sum("quantity"))
        }

        top_products_qs = (
            base_qs
            .values("contract_product__product__designation")
            .annotate(total=Sum("pts"))
            .order_by("-total")[:30]
        )

        submit_map = {
            r["month"].strftime("%Y-%m"): r["batches"]
            for r in SaleImport.objects.filter(
                account_code=account.code,
                received_at__gte=month_dates[0],
            ).annotate(month=TruncMonth("received_at")).values("month")
            .annotate(batches=Count("batch_id", distinct=True))
        }

        month_keys = [d.strftime("%Y-%m") for d in month_dates]

        d_pts_all    = defaultdict(dict)
        d_prods_all  = defaultdict(dict)
        d_units_all  = defaultdict(dict)
        d_batches_all = defaultdict(dict)

        for r in (
            base_qs.annotate(day=TruncDay("sale_datetime"))
            .values("day").annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
        ):
            d_pts_all[r["day"].strftime("%Y-%m")][r["day"].day]   = int(r["total"] or 0)
            d_prods_all[r["day"].strftime("%Y-%m")][r["day"].day] = r["unique_products"]

        for r in (
            Sale.objects.filter(
                contract_product__contract__account=account,
                status=Sale.STATUS_ACCEPTED,
            ).annotate(day=TruncDay("sale_datetime")).values("day").annotate(total=Sum("quantity"))
        ):
            d_units_all[r["day"].strftime("%Y-%m")][r["day"].day] = int(r["total"] or 0)

        for r in (
            SaleImport.objects.filter(account_code=account.code)
            .annotate(day=TruncDay("received_at")).values("day")
            .annotate(batches=Count("batch_id", distinct=True))
        ):
            d_batches_all[r["day"].strftime("%Y-%m")][r["day"].day] = r["batches"]

        all_mk        = set(d_pts_all) | set(d_units_all) | set(d_batches_all)
        daily_drill   = {}
        submit_drill  = {}
        for mk in all_mk:
            yr, mo = int(mk[:4]), int(mk[5:])
            n = cal.monthrange(yr, mo)[1]
            daily_drill[mk]  = {
                "n":     n,
                "pts":   [d_pts_all[mk].get(d, 0) for d in range(1, n + 1)],
                "prods": [d_prods_all[mk].get(d, 0) for d in range(1, n + 1)],
                "units": [d_units_all[mk].get(d, 0) for d in range(1, n + 1)],
            }
            submit_drill[mk] = {
                "n":       n,
                "batches": [d_batches_all[mk].get(d, 0) for d in range(1, n + 1)],
            }

        years_qs = (
            Sale.objects.filter(contract_product__contract__account=account)
            .annotate(yr=TruncYear("sale_datetime")).values("yr").distinct().order_by("yr")
        )
        years_list = [r["yr"].year for r in years_qs if r["yr"]]

        current_year  = now.year
        current_month = now.month
        cumul_carry   = cumul_base
        years_monthly = {}
        years_submit  = {}
        for yr in years_list:
            max_month = current_month if yr == current_year else 12
            yr_months = [datetime.datetime(yr, m, 1, tzinfo=datetime.timezone.utc) for m in range(1, max_month + 1)]
            yr_keys   = [d.strftime("%Y-%m") for d in yr_months]

            yr_monthly_qs = list(
                base_qs.filter(sale_datetime__year=yr)
                .annotate(month=TruncMonth("sale_datetime"))
                .values("month")
                .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
            )
            yr_pts_map      = {r["month"].strftime("%Y-%m"): int(r["total"] or 0) for r in yr_monthly_qs}
            yr_products_map = {r["month"].strftime("%Y-%m"): r["unique_products"] for r in yr_monthly_qs}
            yr_units_map    = {
                r["month"].strftime("%Y-%m"): int(r["total"] or 0)
                for r in Sale.objects.filter(
                    contract_product__contract__account=account,
                    status=Sale.STATUS_ACCEPTED,
                    sale_datetime__year=yr,
                ).annotate(month=TruncMonth("sale_datetime")).values("month").annotate(total=Sum("quantity"))
            }
            yr_submit_map = {
                r["month"].strftime("%Y-%m"): r["batches"]
                for r in SaleImport.objects.filter(
                    account_code=account.code,
                    received_at__year=yr,
                ).annotate(month=TruncMonth("received_at")).values("month")
                .annotate(batches=Count("batch_id", distinct=True))
            }
            yr_pts   = [yr_pts_map.get(k, 0) for k in yr_keys]
            yr_units = [yr_units_map.get(k, 0) for k in yr_keys]

            acc = cumul_carry
            yr_cumul = []
            for p in yr_pts:
                acc += p
                yr_cumul.append(acc)
            cumul_carry = acc

            years_monthly[str(yr)] = {
                "keys":     yr_keys,
                "labels":   [d.strftime("%b") for d in yr_months],
                "pts":      yr_pts,
                "units":    yr_units,
                "cumul":    yr_cumul,
                "products": [yr_products_map.get(k, 0) for k in yr_keys],
            }
            years_submit[str(yr)] = {
                "labels": [d.strftime("%b") for d in yr_months],
                "counts": [yr_submit_map.get(k, 0) for k in yr_keys],
            }

        return Response({
            "month_keys":          month_keys,
            "month_labels":        [d.strftime("%b %Y") for d in month_dates],
            "month_pts":           [monthly_map.get(k, 0) for k in month_keys],
            "month_units":         [units_map.get(k, 0) for k in month_keys],
            "month_products":      [monthly_products_map.get(k, 0) for k in month_keys],
            "top_product_labels":  [r["contract_product__product__designation"] for r in top_products_qs],
            "top_product_data":    [int(r["total"] or 0) for r in top_products_qs],
            "submit_data":         [submit_map.get(k, 0) for k in month_keys],
            "submit_drill":        submit_drill,
            "daily_drill":         daily_drill,
            "years_monthly":       years_monthly,
            "years_submit":        years_submit,
            "cumul_base":          cumul_base,
        })


# ---------------------------------------------------------------------------
# GET /api/portal/dashboard/recent-sales/
# ---------------------------------------------------------------------------

class DashboardRecentSalesView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account = _get_account(request)
        sales = (
            get_account_points_queryset(account)
            .select_related(
                "contract_product__product",
                "contract_product__contract",
            )
            .order_by("-sale_datetime")[:5]
        )
        return Response({"items": SaleSerializer(sales, many=True).data})


# ---------------------------------------------------------------------------
# GET /api/portal/contracts/
# ---------------------------------------------------------------------------

class PortalContractsListView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account = _get_account(request)

        pts_by_contract = {
            r["contract_product__contract_id"]: int(r["total"] or 0)
            for r in get_account_points_queryset(account)
            .values("contract_product__contract_id").annotate(total=Sum("pts"))
        }
        units_by_contract = {
            r["contract_product__contract_id"]: int(r["total"] or 0)
            for r in Sale.objects.filter(
                contract_product__contract__account=account,
                status=Sale.STATUS_ACCEPTED,
            ).values("contract_product__contract_id").annotate(total=Sum("quantity"))
        }
        count_by_contract = {
            r["contract_id"]: r["cnt"]
            for r in Contract_Product.objects.filter(
                contract__account=account
            ).values("contract_id").annotate(cnt=Count("id"))
        }

        qs        = account.contracts.order_by("-status", "-start_date")
        paginator = Paginator(qs, 25)
        page      = paginator.get_page(request.GET.get("page", 1))

        active = account.contracts.filter(status=Contract.STATUS_ACTIVE).first()

        contracts = []
        for c in page:
            c.total_points  = pts_by_contract.get(c.pk, 0)
            c.total_units   = units_by_contract.get(c.pk, 0)
            c.product_count = count_by_contract.get(c.pk, 0)
            contracts.append(c)

        return Response({
            "contracts": ContractListItemSerializer(contracts, many=True).data,
            "total":     paginator.count,
            "page":      page.number,
            "pages":     paginator.num_pages,
            "active_id": active.pk if active else None,
        })


# ---------------------------------------------------------------------------
# GET /api/portal/contracts/active/
# ---------------------------------------------------------------------------

class PortalActiveContractView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account  = _get_account(request)
        contract = account.contracts.filter(status=Contract.STATUS_ACTIVE).first()
        if not contract:
            return Response({"contract": None})

        pts_agg = {
            r["contract_product_id"]: int(r["total_pts"] or 0)
            for r in get_account_points_queryset(account)
            .filter(contract_product__contract=contract)
            .values("contract_product_id").annotate(total_pts=Sum("pts"))
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
        annotated_cps = []
        for cp in cps:
            cp.units_sold     = units_agg.get(cp.pk, 0)
            cp.accepted_units = accepted_units_agg.get(cp.pk, 0)
            cp.points         = pts_agg.get(cp.pk, 0)
            annotated_cps.append(cp)

        total_points = sum(pts_agg.get(cp.pk, 0) for cp in cps)
        total_units  = sum(units_agg.get(cp.pk, 0) for cp in cps)

        return Response({
            "contract": {
                "id":           contract.pk,
                "title":        contract.title,
                "start_date":   contract.start_date,
                "end_date":     contract.end_date,
                "status":       contract.status,
                "total_points": total_points,
                "total_units":  total_units,
                "product_count": len(annotated_cps),
                "products":     ContractProductSerializer(annotated_cps, many=True).data,
            }
        })


# ---------------------------------------------------------------------------
# GET /api/portal/contracts/<pk>/charts/
# ---------------------------------------------------------------------------

class ContractChartsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request, pk):
        account  = _get_account(request)
        contract = get_object_or_404(Contract, pk=pk, account=account)

        base_qs = get_account_points_queryset(account)

        pts_by_contract = {
            r["contract_product__contract_id"]: int(r["total"] or 0)
            for r in base_qs.values("contract_product__contract_id").annotate(total=Sum("pts"))
        }

        contracts_order  = account.contracts.order_by("start_date")
        contract_labels  = [c.title for c in contracts_order]
        contract_data    = [pts_by_contract.get(c.pk, 0) for c in contracts_order]

        active_contract = account.contracts.filter(status=Contract.STATUS_ACTIVE).first()

        cp_pts_agg = {
            r["contract_product_id"]: int(r["total_pts"] or 0)
            for r in get_account_points_queryset(account)
            .filter(contract_product__contract=contract)
            .values("contract_product_id").annotate(total_pts=Sum("pts"))
        }
        cps = (
            Contract_Product.objects.filter(contract=contract)
            .select_related("product").order_by("product__designation")
        )
        product_labels = [cp.product.designation for cp in sorted(cps, key=lambda cp: -cp_pts_agg.get(cp.pk, 0))]
        product_data   = [cp_pts_agg.get(cp.pk, 0) for cp in sorted(cps, key=lambda cp: -cp_pts_agg.get(cp.pk, 0))]

        now = timezone.now()
        if active_contract and active_contract.pk == contract.pk:
            start_d  = active_contract.start_date.date() if hasattr(active_contract.start_date, "date") else active_contract.start_date
            end_d    = active_contract.end_date.date() if hasattr(active_contract.end_date, "date") else active_contract.end_date
            end_bound = end_d
            month_dates = []
            cur = datetime.datetime(start_d.year, start_d.month, 1, tzinfo=datetime.timezone.utc)
            end_dt = datetime.datetime(end_bound.year, end_bound.month, 1, tzinfo=datetime.timezone.utc)
            while cur <= end_dt:
                month_dates.append(cur)
                cur = (cur.replace(month=cur.month + 1) if cur.month < 12
                       else cur.replace(year=cur.year + 1, month=1))
            if not month_dates:
                month_dates = [datetime.datetime(start_d.year, start_d.month, 1, tzinfo=datetime.timezone.utc)]
            period_label = (
                (month_dates[0].strftime("%b %Y") if month_dates[0].strftime("%b %Y") == month_dates[-1].strftime("%b %Y")
                 else month_dates[0].strftime("%b %Y") + " – " + month_dates[-1].strftime("%b %Y"))
                + " · active contract"
            )
        else:
            month_dates = _build_month_dates(12)
            period_label = "Last 12 months"

        month_keys = [d.strftime("%Y-%m") for d in month_dates]

        month_pts   = [0] * len(month_dates)
        month_prods = [0] * len(month_dates)

        contract_pts_qs = get_account_points_queryset(account).filter(contract_product__contract=contract)
        if month_dates:
            mqs = (
                contract_pts_qs
                .filter(sale_datetime__gte=month_dates[0])
                .annotate(month=TruncMonth("sale_datetime"))
                .values("month")
                .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
            )
            mmap      = {r["month"].strftime("%Y-%m"): r for r in mqs}
            month_pts   = [int(mmap.get(k, {}).get("total") or 0) for k in month_keys]
            month_prods = [mmap.get(k, {}).get("unique_products") or 0 for k in month_keys]

        daily_by_month = {}
        if month_dates:
            daily_qs = (
                contract_pts_qs
                .filter(sale_datetime__gte=month_dates[0])
                .annotate(day=TruncDay("sale_datetime"))
                .values("day")
                .annotate(dpts=Sum("pts"), dprods=Count("contract_product__product", distinct=True))
            )
            day_map = {}
            for r in daily_qs:
                mk    = r["day"].strftime("%Y-%m")
                d_int = r["day"].day
                if mk not in day_map:
                    day_map[mk] = {"pts": {}, "prods": {}}
                day_map[mk]["pts"][d_int]   = int(r["dpts"] or 0)
                day_map[mk]["prods"][d_int] = int(r["dprods"] or 0)
            for mk in month_keys:
                if mk in day_map:
                    yr, mo   = int(mk[:4]), int(mk[5:])
                    num_days = cal.monthrange(yr, mo)[1]
                    daily_by_month[mk] = {
                        "n":     num_days,
                        "pts":   [day_map[mk]["pts"].get(d, 0) for d in range(1, num_days + 1)],
                        "prods": [day_map[mk]["prods"].get(d, 0) for d in range(1, num_days + 1)],
                    }

        products_by_month = {}
        prod_month_qs = (
            contract_pts_qs
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month", "contract_product__product__designation")
            .annotate(total=Sum("pts"))
            .order_by("month", "-total")
        )
        for r in prod_month_qs:
            mk = r["month"].strftime("%Y-%m")
            if mk not in products_by_month:
                products_by_month[mk] = []
            products_by_month[mk].append({
                "name": r["contract_product__product__designation"],
                "pts":  int(r["total"] or 0),
            })

        return Response({
            "contract_labels":  contract_labels,
            "contract_data":    contract_data,
            "product_labels":   product_labels,
            "product_data":     product_data,
            "month_keys":       month_keys,
            "month_labels":     [d.strftime("%b %Y") for d in month_dates],
            "month_pts":        month_pts,
            "month_prods":      month_prods,
            "daily_by_month":   daily_by_month,
            "products_by_month": products_by_month,
            "period_label":     period_label,
        })


# ---------------------------------------------------------------------------
# GET /api/portal/sales/stats/
# ---------------------------------------------------------------------------

class PortalSalesStatsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account  = _get_account(request)
        base     = Sale.objects.filter(contract_product__contract__account=account)
        accepted = base.filter(status=Sale.STATUS_ACCEPTED).count()
        rejected = base.filter(status=Sale.STATUS_REJECTED).count()
        pending  = base.filter(status=Sale.STATUS_PENDING).count()
        return Response({
            "total":    accepted + rejected + pending,
            "accepted": accepted,
            "pending":  pending,
            "rejected": rejected,
        })


# ---------------------------------------------------------------------------
# GET /api/portal/sales/
# ---------------------------------------------------------------------------

class PortalSalesListView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account = _get_account(request)

        qs = (
            Sale.objects
            .filter(contract_product__contract__account=account)
            .select_related(
                "contract_product__product",
                "contract_product__contract",
            )
            .annotate(pts=Round(ExpressionWrapper(
                F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
                output_field=FloatField(),
            )))
            .order_by("-sale_datetime")
        )

        status_f = request.GET.get("status", "").strip()
        product  = request.GET.get("product", "").strip()
        date_from = request.GET.get("date_from", "").strip()
        date_to   = request.GET.get("date_to", "").strip()
        contract_id = request.GET.get("contract", "").strip()

        if status_f in (Sale.STATUS_ACCEPTED, Sale.STATUS_REJECTED, Sale.STATUS_PENDING):
            qs = qs.filter(status=status_f)
        if product:
            qs = qs.filter(contract_product__product__designation__icontains=product)
        if date_from:
            qs = qs.filter(sale_datetime__date__gte=date_from)
        if date_to:
            qs = qs.filter(sale_datetime__date__lte=date_to)
        if contract_id:
            get_object_or_404(Contract, pk=contract_id, account=account)
            qs = qs.filter(contract_product__contract_id=contract_id)

        try:
            page_size = min(int(request.GET.get("page_size", 25)), 100)
        except ValueError:
            page_size = 25

        paginator = Paginator(qs, page_size)
        page      = paginator.get_page(request.GET.get("page", 1))

        return Response({
            "items":    SaleSerializer(page.object_list, many=True).data,
            "total":    paginator.count,
            "page":     page.number,
            "pages":    paginator.num_pages,
            "has_prev": page.has_previous(),
            "has_next": page.has_next(),
        })


# ---------------------------------------------------------------------------
# GET /api/portal/sales/charts/
# ---------------------------------------------------------------------------

class SalesChartsView(APIView):
    authentication_classes = _AUTH
    permission_classes     = _PERMS
    throttle_classes       = []

    def get(self, request):
        account     = _get_account(request)
        now         = timezone.now()
        month_dates = _build_month_dates(12)

        monthly_qs = (
            Sale.objects.filter(
                contract_product__contract__account=account,
                sale_datetime__gte=month_dates[0],
            )
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month", "status")
            .annotate(cnt=Count("id"))
        )
        m_acc  = defaultdict(int)
        m_rej  = defaultdict(int)
        m_pend = defaultdict(int)
        for r in monthly_qs:
            mk = r["month"].strftime("%Y-%m")
            if r["status"] == Sale.STATUS_ACCEPTED:
                m_acc[mk] += r["cnt"]
            elif r["status"] == Sale.STATUS_REJECTED:
                m_rej[mk] += r["cnt"]
            else:
                m_pend[mk] += r["cnt"]

        month_keys = [d.strftime("%Y-%m") for d in month_dates]

        years_qs = (
            Sale.objects.filter(contract_product__contract__account=account)
            .annotate(yr=TruncYear("sale_datetime")).values("yr").distinct().order_by("yr")
        )
        years_list = [r["yr"].year for r in years_qs if r["yr"]]

        years_data = {}
        for yr in years_list:
            yr_months = [datetime.datetime(yr, m, 1, tzinfo=datetime.timezone.utc) for m in range(1, 13)]
            yr_qs     = (
                Sale.objects.filter(
                    contract_product__contract__account=account,
                    sale_datetime__year=yr,
                )
                .annotate(month=TruncMonth("sale_datetime"))
                .values("month", "status").annotate(cnt=Count("id"))
            )
            ya = defaultdict(int); yr_rej = defaultdict(int); yp = defaultdict(int)
            for r in yr_qs:
                mk = r["month"].strftime("%Y-%m")
                if r["status"] == Sale.STATUS_ACCEPTED:
                    ya[mk] += r["cnt"]
                elif r["status"] == Sale.STATUS_REJECTED:
                    yr_rej[mk] += r["cnt"]
                else:
                    yp[mk] += r["cnt"]
            years_data[str(yr)] = {
                "keys":     [d.strftime("%Y-%m") for d in yr_months],
                "labels":   [d.strftime("%b") for d in yr_months],
                "accepted": [ya.get(d.strftime("%Y-%m"), 0) for d in yr_months],
                "rejected": [yr_rej.get(d.strftime("%Y-%m"), 0) for d in yr_months],
                "pending":  [yp.get(d.strftime("%Y-%m"), 0) for d in yr_months],
            }

        daily_qs = (
            Sale.objects.filter(contract_product__contract__account=account)
            .annotate(day=TruncDay("sale_datetime"))
            .values("day", "status").annotate(cnt=Count("id"))
        )
        daily_map = {}
        for r in daily_qs:
            mk    = r["day"].strftime("%Y-%m")
            d_int = r["day"].day
            if mk not in daily_map:
                daily_map[mk] = {"acc": {}, "rej": {}, "pend": {}}
            bucket = (
                "acc"  if r["status"] == Sale.STATUS_ACCEPTED else
                "rej"  if r["status"] == Sale.STATUS_REJECTED else
                "pend"
            )
            daily_map[mk][bucket][d_int] = daily_map[mk][bucket].get(d_int, 0) + r["cnt"]

        drill_data = {}
        for mk, buckets in daily_map.items():
            yr, mo   = int(mk[:4]), int(mk[5:])
            num_days = cal.monthrange(yr, mo)[1]
            drill_data[mk] = {
                "labels":   list(range(1, num_days + 1)),
                "accepted": [buckets["acc"].get(d, 0) for d in range(1, num_days + 1)],
                "rejected": [buckets["rej"].get(d, 0) for d in range(1, num_days + 1)],
                "pending":  [buckets["pend"].get(d, 0) for d in range(1, num_days + 1)],
            }

        return Response({
            "month_keys":       month_keys,
            "month_labels":     [d.strftime("%b %Y") for d in month_dates],
            "month_accepted":   [m_acc.get(k, 0) for k in month_keys],
            "month_rejected":   [m_rej.get(k, 0) for k in month_keys],
            "month_pending":    [m_pend.get(k, 0) for k in month_keys],
            "years_data":       years_data,
            "drill_data":       drill_data,
        })
