from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.contrib.auth.models import User
from .models import UserProfile
import secrets
from django.utils import timezone
from django.core.mail import send_mail

from django.conf import settings


def custom_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("/control/")
        return redirect("/portal/dashboard/")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_staff:
                try:
                    account = user.profile.account
                    if not account.pharmacy_portal:
                        request.session["login_error"] = "Your account does not have portal access."
                        return redirect("/portal/login/")
                except:
                    request.session["login_error"] = "Your account is not linked to any pharmacy."
                    return redirect("/portal/login/")

            login(request, user)

            if user.is_staff:
                return redirect("/control/")
            else:
                return redirect("/portal/dashboard/")
        else:
            request.session["login_error"] = "Invalid username or password."
            return redirect("/portal/login/")

    error = request.session.pop("login_error", None)
    if error:
        messages.error(request, error)

    return render(request, "fidpha/login.html")


def custom_logout(request):
    logout(request)
    messages.success(request, "You have been successfully signed out.")
    return redirect("/portal/login/")


def admin_welcome(request):
    welcome = request.session.pop("welcome_message", None)
    if welcome:
        messages.success(request, welcome)
    return redirect("/control/")


@login_required(login_url="/portal/login/")
def setup_profile(request):
    if request.user.is_staff:
        return redirect("/control/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "").strip()

        # update name
        request.user.first_name = first_name
        request.user.last_name = last_name

        if email:
            # check email not already used
            if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                messages.error(request, "This email is already used by another account.")
                return redirect("/portal/setup-profile/")

            # send verification email
            token = secrets.token_urlsafe(32)
            profile.verification_token = token
            profile.token_created_at = timezone.now()
            profile.save()

            verify_url = f"{request.scheme}://{request.get_host()}/portal/verify-email/{token}/"
            try:
                send_mail(
                    "WinInPharma — Verify your email",
                    f"Click the link to verify your email: {verify_url}",
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                request.user.email = email
                request.user.save()
                messages.success(request, "Verification email sent!")
                return redirect("/portal/verify-pending/")
            except Exception as e:
                messages.error(request, f"Failed to send email: {str(e)}")
                return redirect("/portal/setup-profile/")

        if password:
            request.user.set_password(password)
            request.user.save()
            login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
        else:
            request.user.save()

        return redirect("/portal/dashboard/")

    return render(request, "fidpha/setup_profile.html")



@login_required(login_url="/portal/login/")
def portal_profile(request):
    if request.user.is_staff:
        return redirect("/control/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")

        # only validate and process email if one was provided
        if email:
            if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                messages.error(request, "This email is already used by another account.")
                return redirect("/portal/pharmacy/")

            if email != request.user.email:
                profile.email_verified = False
                token = secrets.token_urlsafe(32)
                profile.verification_token = token
                profile.token_created_at = timezone.now()
                profile.save()

                from allauth.socialaccount.models import SocialAccount
                SocialAccount.objects.filter(user=request.user).delete()

                verify_url = f"{request.scheme}://{request.get_host()}/portal/verify-email/{token}/"
                try:
                    send_mail(
                        "WinInPharma — Verify your new email",
                        f"Click the link to verify your new email: {verify_url}",
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                    )
                    messages.success(request, "Verification email sent to your new address!")
                except Exception as e:
                    messages.error(request, f"Failed to send email: {str(e)}")
                    return redirect("/portal/pharmacy/")

            request.user.email = email

        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()

        if not email:
            messages.success(request, "Profile updated successfully!")

        return redirect("/portal/pharmacy/")

    return render(request, "fidpha/profile.html", {
        "profile": profile,
    })




@login_required(login_url="/portal/login/")
def portal_profile_password(request):
    if request.user.is_staff:
        return redirect("/control/")

    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # verify current password
        if not request.user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect("/portal/pharmacy/")

        # check new passwords match
        if new_password != confirm_password:
            messages.error(request, "New passwords don't match.")
            return redirect("/portal/pharmacy/")

        # validate strength
        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return redirect("/portal/pharmacy/")
        if new_password.isdigit():
            messages.error(request, "Password can't be entirely numeric.")
            return redirect("/portal/pharmacy/")
        if not any(c.isupper() for c in new_password):
            messages.error(request, "Password must contain at least one uppercase letter.")
            return redirect("/portal/pharmacy/")
        if not any(c.isdigit() for c in new_password):
            messages.error(request, "Password must contain at least one number.")
            return redirect("/portal/pharmacy/")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in new_password):
            messages.error(request, "Password must contain at least one special character.")
            return redirect("/portal/pharmacy/")

        request.user.set_password(new_password)
        request.user.save()
        login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, "Password updated successfully!")
        return redirect("/portal/pharmacy/")

    return redirect("/portal/profile/")



@login_required(login_url="/portal/login/")
def verify_pending(request):
    if request.user.is_staff:
        return redirect("/control/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    if profile.email_verified:
        return redirect("/portal/dashboard/")

    if not request.user.email:
        return render(request, "fidpha/verify_pending.html", {"no_email": True})

    # always generate a fresh token and resend
    token = secrets.token_urlsafe(32)
    profile.verification_token = token
    profile.token_created_at = timezone.now()
    profile.save()

    verify_url = f"{request.scheme}://{request.get_host()}/portal/verify-email/{token}/"
    try:
        send_mail(
            "WinInPharma — Verify your email",
            f"Click the link to verify your email: {verify_url}",
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=False,
        )
    except Exception as e:
        messages.error(request, f"Failed to send email: {str(e)}")
        return redirect("/portal/dashboard/")

    return render(request, "fidpha/verify_pending.html", {"no_email": False})




def verify_email(request, token):
    try:
        profile = UserProfile.objects.get(verification_token=token)
    except UserProfile.DoesNotExist:
        messages.error(request, "Invalid verification link.")
        return redirect("/portal/login/")

    if timezone.now() - profile.token_created_at > timezone.timedelta(hours=24):
        messages.error(request, "Verification link has expired. Please request a new one.")
        return redirect("/portal/setup-profile/")

    profile.email_verified = True
    profile.verification_token = None
    profile.token_created_at = None
    profile.save()

    messages.success(request, "Email verified successfully! You can now log in.")
    return redirect("/portal/login/")


@login_required(login_url="/portal/login/")
def portal_dashboard(request):
    if request.user.is_staff:
        return redirect("/control/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    import json
    import datetime
    from django.utils import timezone
    from sales.models import Sale, SaleImport
    from django.db.models import Sum, F, ExpressionWrapper, FloatField, Count
    from django.db.models.functions import TruncMonth, TruncDay, Round

    account = profile.account

    base_qs = Sale.objects.filter(
        contract_product__contract__account=account,
        status=Sale.STATUS_ACCEPTED,
        product_ppv__isnull=False,
    ).annotate(
        pts=Round(ExpressionWrapper(
            F("quantity") * F("product_ppv") * F("contract_product__points_per_unit"),
            output_field=FloatField(),
        ))
    )

    total_points = int(base_qs.aggregate(total=Sum("pts"))["total"] or 0)

    def _fmt_big(v):
        if v >= 1_000_000:
            s = f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".")
            return f"{s}M"
        if v >= 1000:
            s = f"{v / 1000:.1f}".rstrip("0").rstrip(".")
            return f"{s}K"
        return str(v)
    total_points_display = _fmt_big(total_points)

    now = timezone.now()
    month_dates = []
    for i in range(11, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        month_dates.append(datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc))

    # Points earned before the 12-month window — used as the cumulative baseline
    chart_cumul_base = int(
        base_qs.filter(sale_datetime__lt=month_dates[0])
        .aggregate(t=Sum("pts"))["t"] or 0
    )

    monthly_qs = (
        base_qs.filter(sale_datetime__gte=month_dates[0])
        .annotate(month=TruncMonth("sale_datetime"))
        .values("month")
        .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
        .order_by("month")
    )
    monthly_map          = {r["month"].strftime("%Y-%m"): int(r["total"] or 0) for r in monthly_qs}
    monthly_products_map = {r["month"].strftime("%Y-%m"): r["unique_products"] for r in monthly_qs}
    chart_month_labels   = [d.strftime("%b %Y") for d in month_dates]
    chart_month_data     = [monthly_map.get(d.strftime("%Y-%m"), 0) for d in month_dates]
    chart_month_products = [monthly_products_map.get(d.strftime("%Y-%m"), 0) for d in month_dates]

    # Monthly units sold
    monthly_units_qs = (
        Sale.objects.filter(
            contract_product__contract__account=account,
            status=Sale.STATUS_ACCEPTED,
            sale_datetime__gte=month_dates[0],
        )
        .annotate(month=TruncMonth("sale_datetime"))
        .values("month")
        .annotate(total=Sum("quantity"))
        .order_by("month")
    )
    units_map = {r["month"].strftime("%Y-%m"): int(r["total"] or 0) for r in monthly_units_qs}
    chart_month_units = [units_map.get(d.strftime("%Y-%m"), 0) for d in month_dates]

    # Top products by points earned
    top_products_qs = (
        base_qs
        .values("contract_product__product__designation")
        .annotate(total=Sum("pts"))
        .order_by("-total")[:30]
    )
    top_product_labels = [r["contract_product__product__designation"] for r in top_products_qs]
    top_product_data   = [int(r["total"] or 0) for r in top_products_qs]

    # Submission frequency — distinct batch_ids per month (last 12)
    submit_qs = (
        SaleImport.objects.filter(
            account_code=account.code,
            received_at__gte=month_dates[0],
        )
        .annotate(month=TruncMonth("received_at"))
        .values("month")
        .annotate(batches=Count("batch_id", distinct=True))
        .order_by("month")
    )
    submit_map = {r["month"].strftime("%Y-%m"): r["batches"] for r in submit_qs}
    chart_submit_data = [submit_map.get(d.strftime("%Y-%m"), 0) for d in month_dates]
    chart_month_keys  = [d.strftime("%Y-%m") for d in month_dates]

    import calendar
    from collections import defaultdict
    from django.db.models.functions import TruncYear

    # ── Unified daily drill (all time) keyed by YYYY-MM ──
    d_pts_all    = defaultdict(dict)
    d_units_all  = defaultdict(dict)
    d_batches_all = defaultdict(dict)

    for r in (
        base_qs.annotate(day=TruncDay("sale_datetime"))
        .values("day").annotate(total=Sum("pts")).order_by("day")
    ):
        d_pts_all[r["day"].strftime("%Y-%m")][r["day"].day] = int(r["total"] or 0)

    for r in (
        Sale.objects.filter(contract_product__contract__account=account, status=Sale.STATUS_ACCEPTED)
        .annotate(day=TruncDay("sale_datetime"))
        .values("day").annotate(total=Sum("quantity")).order_by("day")
    ):
        d_units_all[r["day"].strftime("%Y-%m")][r["day"].day] = int(r["total"] or 0)

    for r in (
        SaleImport.objects.filter(account_code=account.code)
        .annotate(day=TruncDay("received_at"))
        .values("day").annotate(batches=Count("batch_id", distinct=True)).order_by("day")
    ):
        d_batches_all[r["day"].strftime("%Y-%m")][r["day"].day] = r["batches"]

    all_mk = set(d_pts_all) | set(d_units_all) | set(d_batches_all)
    chart_daily_drill  = {}
    chart_submit_drill = {}
    for mk in all_mk:
        parts = mk.split("-")
        yr, mo = int(parts[0]), int(parts[1])
        n = calendar.monthrange(yr, mo)[1]
        chart_daily_drill[mk]  = {"n": n,
            "pts":     [d_pts_all[mk].get(d, 0) for d in range(1, n+1)],
            "units":   [d_units_all[mk].get(d, 0) for d in range(1, n+1)]}
        chart_submit_drill[mk] = {"n": n,
            "batches": [d_batches_all[mk].get(d, 0) for d in range(1, n+1)]}

    # ── Per-year monthly data (for year selectors) ──
    years_qs = (
        Sale.objects.filter(contract_product__contract__account=account)
        .annotate(yr=TruncYear("sale_datetime"))
        .values("yr").distinct().order_by("yr")
    )
    dash_years_list = [r["yr"].year for r in years_qs if r["yr"]]

    dash_years_monthly = {}
    dash_years_submit  = {}
    current_year  = now.year
    current_month = now.month
    cumul_carry = 0  # running total carried from all years before the current one
    for yr in dash_years_list:
        max_month = current_month if yr == current_year else 12
        yr_months = [datetime.datetime(yr, m, 1, tzinfo=datetime.timezone.utc) for m in range(1, max_month + 1)]
        yr_keys   = [d.strftime("%Y-%m") for d in yr_months]
        yr_labels = [d.strftime("%b") for d in yr_months]

        yr_monthly_qs = list(
            base_qs.filter(sale_datetime__year=yr)
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month")
            .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
            .order_by("month")
        )
        yr_pts_map      = {r["month"].strftime("%Y-%m"): int(r["total"] or 0) for r in yr_monthly_qs}
        yr_products_map = {r["month"].strftime("%Y-%m"): r["unique_products"] for r in yr_monthly_qs}
        yr_units_map = {r["month"].strftime("%Y-%m"): int(r["total"] or 0) for r in (
            Sale.objects.filter(
                contract_product__contract__account=account,
                status=Sale.STATUS_ACCEPTED, sale_datetime__year=yr,
            )
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month").annotate(total=Sum("quantity")).order_by("month")
        )}
        yr_submit_map = {r["month"].strftime("%Y-%m"): r["batches"] for r in (
            SaleImport.objects.filter(account_code=account.code, received_at__year=yr)
            .annotate(month=TruncMonth("received_at"))
            .values("month").annotate(batches=Count("batch_id", distinct=True)).order_by("month")
        )}
        yr_pts   = [yr_pts_map.get(k, 0) for k in yr_keys]
        yr_units = [yr_units_map.get(k, 0) for k in yr_keys]
        acc = cumul_carry; yr_cumul = []
        for p in yr_pts: acc += p; yr_cumul.append(acc)
        cumul_carry = acc  # carry this year's final total into the next year

        yr_products = [yr_products_map.get(k, 0) for k in yr_keys]
        dash_years_monthly[str(yr)] = {
            "keys": yr_keys, "labels": yr_labels,
            "pts": yr_pts, "units": yr_units, "cumul": yr_cumul,
            "products": yr_products,
        }
        dash_years_submit[str(yr)] = {
            "labels": yr_labels,
            "counts": [yr_submit_map.get(k, 0) for k in yr_keys],
        }

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_pts = int(
        base_qs.filter(sale_datetime__gte=month_start).aggregate(t=Sum("pts"))["t"] or 0
    )
    this_month_units = int(
        Sale.objects.filter(
            contract_product__contract__account=account,
            status=Sale.STATUS_ACCEPTED,
            sale_datetime__gte=month_start,
        ).aggregate(t=Sum("quantity"))["t"] or 0
    )
    active_contract = account.contracts.filter(status="active").first()
    total_products_count = base_qs.values("contract_product__product").distinct().count()
    total_contracts_count = account.contracts.count()
    recent_sales = (
        Sale.objects
        .filter(contract_product__contract__account=account)
        .select_related("contract_product__product", "contract_product__contract")
        .annotate(
            pts=Round(ExpressionWrapper(
                F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
                output_field=FloatField(),
            ))
        )
        .order_by("-sale_datetime")[:5]
    )

    return render(request, "fidpha/dashboard.html", {
        "account":                account,
        "email_verified":         profile.email_verified,
        "total_points":           total_points,
        "total_points_display":   total_points_display,
        "this_month_pts":         _fmt_big(this_month_pts),
        "this_month_units":       this_month_units,
        "active_contract":        active_contract,
        "total_products_count":   total_products_count,
        "total_contracts_count":  total_contracts_count,
        "recent_sales":           recent_sales,
        "dash_years_list":        dash_years_list,
        "chart_month_keys":       json.dumps(chart_month_keys),
        "chart_month_labels":     json.dumps(chart_month_labels),
        "chart_month_data":       json.dumps(chart_month_data),
        "chart_month_units":      json.dumps(chart_month_units),
        "chart_month_products":   json.dumps(chart_month_products),
        "top_product_labels":     json.dumps(top_product_labels),
        "top_product_data":       json.dumps(top_product_data),
        "chart_submit_data":      json.dumps(chart_submit_data),
        "chart_submit_drill":     json.dumps(chart_submit_drill),
        "chart_daily_drill":      json.dumps(chart_daily_drill),
        "dash_years_monthly":     json.dumps(dash_years_monthly),
        "dash_years_submit":      json.dumps(dash_years_submit),
        "chart_cumul_base":       chart_cumul_base,
    })


@login_required(login_url="/portal/login/")
def portal_pharmacy(request):
    if request.user.is_staff:
        return redirect("/control/")
    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")
    return render(request, "fidpha/pharmacy.html", {
        "account": profile.account,
        "profile": profile,
    })


@login_required(login_url="/portal/login/")
def portal_contracts(request):
    if request.user.is_staff:
        return redirect("/control/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    import json
    import datetime
    import calendar as cal
    from fidpha.models import Contract_Product
    from sales.models import Sale
    from django.utils import timezone
    from django.db.models import Sum, F, ExpressionWrapper, FloatField, Count
    from django.db.models.functions import Round, TruncMonth, TruncDay

    account = profile.account
    active_contract = account.contracts.filter(status="active").first()

    def _pts_qs(extra_filter):
        return (
            Sale.objects.filter(
                status=Sale.STATUS_ACCEPTED,
                product_ppv__isnull=False,
                **extra_filter,
            ).annotate(pts=Round(ExpressionWrapper(
                F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
                output_field=FloatField(),
            )))
        )

    # ── Active contract — per-product breakdown ──
    products_data = []
    active_total_points = 0
    active_total_units  = 0
    active_products_count       = 0
    active_products_with_points = 0

    if active_contract:
        cp_agg = {
            r["contract_product_id"]: r
            for r in (
                _pts_qs({"contract_product__contract": active_contract})
                .values("contract_product_id")
                .annotate(total_pts=Sum("pts"), total_units=Sum("quantity"))
            )
        }
        units_agg = {
            r["contract_product_id"]: int(r["total"] or 0)
            for r in (
                Sale.objects.filter(contract_product__contract=active_contract)
                .values("contract_product_id")
                .annotate(total=Sum("quantity"))
            )
        }
        accepted_units_agg = {
            r["contract_product_id"]: int(r["total"] or 0)
            for r in (
                Sale.objects.filter(
                    contract_product__contract=active_contract,
                    status=Sale.STATUS_ACCEPTED,
                )
                .values("contract_product_id")
                .annotate(total=Sum("quantity"))
            )
        }
        for cp in (Contract_Product.objects
                   .filter(contract=active_contract)
                   .select_related("product")
                   .order_by("product__designation")):
            agg            = cp_agg.get(cp.pk, {})
            points         = int(agg.get("total_pts") or 0)
            units          = units_agg.get(cp.pk, 0)
            accepted_units = accepted_units_agg.get(cp.pk, 0)
            products_data.append({"cp": cp, "units_sold": units, "accepted_units": accepted_units, "points": points})
            active_total_points += points
            active_total_units  += units

        active_products_count       = active_contract.contract_product_set.count()
        active_products_with_points = sum(1 for d in products_data if d["points"] > 0)

    # ── Points per contract (all) ──
    pts_by_contract = {
        r["contract_product__contract_id"]: int(r["total"] or 0)
        for r in (
            _pts_qs({"contract_product__contract__account": account})
            .values("contract_product__contract_id")
            .annotate(total=Sum("pts"))
        )
    }

    # ── Past contracts ──
    past_contracts = []
    for old in account.contracts.exclude(status="active").order_by("-end_date"):
        units = int(
            Sale.objects.filter(contract_product__contract=old)
            .aggregate(t=Sum("quantity"))["t"] or 0
        )
        past_contracts.append({
            "contract":      old,
            "total_points":  pts_by_contract.get(old.pk, 0),
            "total_units":   units,
            "product_count": old.contract_product_set.count(),
        })

    # ── Charts ──
    contracts_chart_order = account.contracts.order_by("start_date")
    chart_contract_labels = [c.title for c in contracts_chart_order]
    chart_contract_data   = [pts_by_contract.get(c.pk, 0) for c in contracts_chart_order]

    products_sorted      = sorted(products_data, key=lambda d: d["points"], reverse=True)
    product_chart_labels = [d["cp"].product.designation for d in products_sorted]
    product_chart_data   = [d["points"] for d in products_sorted]

    # ── Build month range: full contract duration or fallback last 12 ──
    now = timezone.now()
    if active_contract:
        start_d = active_contract.start_date
        end_d   = active_contract.end_date
        if isinstance(start_d, datetime.datetime): start_d = start_d.date()
        if isinstance(end_d,   datetime.datetime): end_d   = end_d.date()
        end_bound = end_d if end_d else now.date()
        month_dates = []
        cur    = datetime.datetime(start_d.year, start_d.month, 1, tzinfo=datetime.timezone.utc)
        end_dt = datetime.datetime(end_bound.year, end_bound.month, 1, tzinfo=datetime.timezone.utc)
        while cur <= end_dt:
            month_dates.append(cur)
            cur = cur.replace(month=cur.month + 1) if cur.month < 12 else cur.replace(year=cur.year + 1, month=1)
        if not month_dates:
            month_dates = [datetime.datetime(start_d.year, start_d.month, 1, tzinfo=datetime.timezone.utc)]
        first_lbl, last_lbl = month_dates[0].strftime("%b %Y"), month_dates[-1].strftime("%b %Y")
        chart_period_label = (first_lbl if first_lbl == last_lbl else first_lbl + " – " + last_lbl) + " · active contract"
    else:
        month_dates = []
        for i in range(11, -1, -1):
            m, y = now.month - i, now.year
            while m <= 0: m += 12; y -= 1
            month_dates.append(datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc))
        chart_period_label = "Last 12 months"

    chart_month_keys  = [d.strftime("%Y-%m") for d in month_dates]
    chart_month_lbls  = [d.strftime("%b %Y") for d in month_dates]
    chart_month_pts   = [0] * len(month_dates)
    chart_month_prods = [0] * len(month_dates)

    if active_contract:
        mqs = (
            _pts_qs({"contract_product__contract": active_contract})
            .filter(sale_datetime__gte=month_dates[0])
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month")
            .annotate(total=Sum("pts"), unique_products=Count("contract_product__product", distinct=True))
        )
        mmap = {r["month"].strftime("%Y-%m"): r for r in mqs}
        chart_month_pts   = [int(mmap.get(k, {}).get("total") or 0) for k in chart_month_keys]
        chart_month_prods = [mmap.get(k, {}).get("unique_products") or 0 for k in chart_month_keys]

    # ── Daily drill-down for monthly trend (active contract) ──
    daily_by_month = {}
    if active_contract:
        daily_qs = (
            _pts_qs({"contract_product__contract": active_contract})
            .filter(sale_datetime__gte=month_dates[0])
            .annotate(day=TruncDay("sale_datetime"))
            .values("day")
            .annotate(dpts=Sum("pts"), dprods=Count("contract_product__product", distinct=True))
            .order_by("day")
        )
        day_map = {}
        for r in daily_qs:
            mk    = r["day"].strftime("%Y-%m")
            d_int = r["day"].day
            if mk not in day_map:
                day_map[mk] = {"pts": {}, "prods": {}}
            day_map[mk]["pts"][d_int]   = int(r["dpts"] or 0)
            day_map[mk]["prods"][d_int] = int(r["dprods"] or 0)
        for mk in chart_month_keys:
            if mk in day_map:
                parts    = mk.split("-")
                yr, mo   = int(parts[0]), int(parts[1])
                num_days = cal.monthrange(yr, mo)[1]
                daily_by_month[mk] = {
                    "n":     num_days,
                    "pts":   [day_map[mk]["pts"].get(d, 0) for d in range(1, num_days + 1)],
                    "prods": [day_map[mk]["prods"].get(d, 0) for d in range(1, num_days + 1)],
                }

    # ── Products by month (for cross-chart filter) ──
    products_by_month = {}
    if active_contract:
        prod_month_qs = (
            _pts_qs({"contract_product__contract": active_contract})
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

    return render(request, "fidpha/contracts.html", {
        "active_contract":              active_contract,
        "products_data":                products_data,
        "active_total_points":          active_total_points,
        "active_total_units":           active_total_units,
        "active_products_count":        active_products_count,
        "active_products_with_points":  active_products_with_points,
        "past_contracts":               past_contracts,
        "chart_contract_labels":        json.dumps(chart_contract_labels),
        "chart_contract_data":          json.dumps(chart_contract_data),
        "product_chart_labels":         json.dumps(product_chart_labels),
        "product_chart_data":           json.dumps(product_chart_data),
        "chart_month_keys":             json.dumps(chart_month_keys),
        "chart_month_labels":           json.dumps(chart_month_lbls),
        "chart_month_pts":              json.dumps(chart_month_pts),
        "chart_month_prods":            json.dumps(chart_month_prods),
        "daily_by_month":               json.dumps(daily_by_month),
        "products_by_month":            json.dumps(products_by_month),
        "chart_period_label":           chart_period_label,
    })




# -----------------------
# Sales / Loyalty
# -----------------------

def _calculate_points(quantity, ppv, factor=1):
    """
    Points rule: round(ppv × quantity × factor).
    factor comes from Contract_Product.points_per_unit (default 1 = 1 pt/MAD).
    ppv is taken from the Product table, not from the sale record.
    Returns 0 if ppv is None.
    """
    if ppv is None:
        return 0
    return round(float(ppv) * quantity * float(factor))


@login_required(login_url="/portal/login/")
def portal_sales(request):
    if request.user.is_staff:
        return redirect("/control/")

    try:
        profile = request.user.profile
    except Exception:
        return redirect("/portal/login/")

    import json
    import datetime
    import calendar as cal
    from collections import defaultdict
    from django.utils import timezone
    from django.db.models import Count, FloatField, ExpressionWrapper, F
    from django.db.models.functions import Round, TruncMonth, TruncDay, TruncYear
    from sales.models import Sale

    account = profile.account
    all_sales = (
        Sale.objects
        .filter(contract_product__contract__account=account)
        .select_related("contract_product__product", "contract_product__contract")
        .annotate(
            points=Round(ExpressionWrapper(
                F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
                output_field=FloatField(),
            ))
        )
        .order_by("-sale_datetime")
    )

    accepted_count = all_sales.filter(status=Sale.STATUS_ACCEPTED).count()
    rejected_count = all_sales.filter(status="rejected").count()
    pending_count  = all_sales.exclude(status=Sale.STATUS_ACCEPTED).exclude(status="rejected").count()
    total_count    = accepted_count + pending_count + rejected_count

    # ── Last 12 months ──
    now = timezone.now()
    month_dates = []
    for i in range(11, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12; y -= 1
        month_dates.append(datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc))

    monthly_qs = (
        Sale.objects.filter(
            contract_product__contract__account=account,
            sale_datetime__gte=month_dates[0],
        )
        .annotate(month=TruncMonth("sale_datetime"))
        .values("month", "status")
        .annotate(cnt=Count("id"))
        .order_by("month")
    )
    m_acc = defaultdict(int); m_rej = defaultdict(int); m_pend = defaultdict(int)
    for r in monthly_qs:
        mk = r["month"].strftime("%Y-%m")
        if r["status"] == Sale.STATUS_ACCEPTED: m_acc[mk] += r["cnt"]
        elif r["status"] == "rejected":         m_rej[mk] += r["cnt"]
        else:                                   m_pend[mk] += r["cnt"]

    sales_month_keys     = [d.strftime("%Y-%m") for d in month_dates]
    sales_month_labels   = [d.strftime("%b %Y") for d in month_dates]
    sales_month_accepted = [m_acc.get(d.strftime("%Y-%m"), 0) for d in month_dates]
    sales_month_rejected = [m_rej.get(d.strftime("%Y-%m"), 0) for d in month_dates]
    sales_month_pending  = [m_pend.get(d.strftime("%Y-%m"), 0) for d in month_dates]

    # ── Per-year monthly data (for year selector) ──
    years_qs = (
        Sale.objects.filter(contract_product__contract__account=account)
        .annotate(yr=TruncYear("sale_datetime"))
        .values("yr").distinct().order_by("yr")
    )
    available_years_list = [r["yr"].year for r in years_qs if r["yr"]]

    years_data = {}
    for yr in available_years_list:
        yr_months = [datetime.datetime(yr, m, 1, tzinfo=datetime.timezone.utc) for m in range(1, 13)]
        yr_qs = (
            Sale.objects.filter(
                contract_product__contract__account=account,
                sale_datetime__year=yr,
            )
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month", "status")
            .annotate(cnt=Count("id"))
            .order_by("month")
        )
        ya = defaultdict(int); yr_rej = defaultdict(int); yp = defaultdict(int)
        for r in yr_qs:
            mk = r["month"].strftime("%Y-%m")
            if r["status"] == Sale.STATUS_ACCEPTED: ya[mk] += r["cnt"]
            elif r["status"] == "rejected":         yr_rej[mk] += r["cnt"]
            else:                                   yp[mk] += r["cnt"]
        years_data[str(yr)] = {
            "keys":     [d.strftime("%Y-%m") for d in yr_months],
            "labels":   [d.strftime("%b") for d in yr_months],
            "accepted": [ya.get(d.strftime("%Y-%m"), 0) for d in yr_months],
            "rejected": [yr_rej.get(d.strftime("%Y-%m"), 0) for d in yr_months],
            "pending":  [yp.get(d.strftime("%Y-%m"), 0) for d in yr_months],
        }

    # ── Daily drill-down data ──
    daily_qs = (
        Sale.objects.filter(contract_product__contract__account=account)
        .annotate(day=TruncDay("sale_datetime"))
        .values("day", "status")
        .annotate(cnt=Count("id"))
        .order_by("day")
    )
    daily_map = {}
    for r in daily_qs:
        mk    = r["day"].strftime("%Y-%m")
        d_int = r["day"].day
        if mk not in daily_map:
            daily_map[mk] = {"acc": {}, "rej": {}, "pend": {}}
        if r["status"] == Sale.STATUS_ACCEPTED: bucket = "acc"
        elif r["status"] == "rejected":         bucket = "rej"
        else:                                   bucket = "pend"
        daily_map[mk][bucket][d_int] = daily_map[mk][bucket].get(d_int, 0) + r["cnt"]

    drill_data = {}
    for mk, buckets in daily_map.items():
        parts = mk.split("-")
        yr, mo = int(parts[0]), int(parts[1])
        num_days = cal.monthrange(yr, mo)[1]
        drill_data[mk] = {
            "labels":   list(range(1, num_days + 1)),
            "accepted": [buckets["acc"].get(d, 0) for d in range(1, num_days + 1)],
            "rejected": [buckets["rej"].get(d, 0) for d in range(1, num_days + 1)],
            "pending":  [buckets["pend"].get(d, 0) for d in range(1, num_days + 1)],
        }

    pharmacy_contracts = list(account.contracts.values("id", "title").order_by("title"))

    return render(request, "fidpha/sales.html", {
        "all_sales":            all_sales,
        "total_count":          total_count,
        "accepted_count":       accepted_count,
        "pending_count":        pending_count,
        "rejected_count":       rejected_count,
        "available_years_list": available_years_list,
        "sales_month_keys":     json.dumps(sales_month_keys),
        "sales_month_labels":   json.dumps(sales_month_labels),
        "sales_month_accepted": json.dumps(sales_month_accepted),
        "sales_month_rejected": json.dumps(sales_month_rejected),
        "sales_month_pending":  json.dumps(sales_month_pending),
        "years_data":           json.dumps(years_data),
        "drill_data":           json.dumps(drill_data),
        "pharmacy_contracts":   pharmacy_contracts,
    })


# -----------------------
# Password Reset
# -----------------------

class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not User.objects.filter(email=email).exists():
            raise ValidationError("No account found with this email address.")
        return email


class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = "registration/password_reset_form.html"
    success_url = reverse_lazy("password_reset_done")

    def form_invalid(self, form):
        self.request.session["reset_errors"] = True
        return redirect("/accounts/password_reset/")

    def get(self, request, *args, **kwargs):
        errors = request.session.pop("reset_errors", None)
        form = self.form_class()
        return render(request, self.template_name, {
            "form": form,
            "session_errors": errors,
        })

# -----------------------
# Password Reset Confirm
# -----------------------

class CustomSetPasswordForm(SetPasswordForm):
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("new_password1")
        password2 = cleaned_data.get("new_password2")

        if password1 and password2:
            if password1 != password2:
                raise ValidationError("The two passwords don't match.")
            if len(password1) < 8:
                raise ValidationError("Password must be at least 8 characters.")
            if password1.isdigit():
                raise ValidationError("Password can't be entirely numeric.")
            if not any(c.isupper() for c in password1):
                raise ValidationError("Password must contain at least one uppercase letter.")
            if not any(c.isdigit() for c in password1):
                raise ValidationError("Password must contain at least one number.")
            if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in password1):
                raise ValidationError("Password must contain at least one special character.")
        return cleaned_data


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = CustomSetPasswordForm
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_invalid(self, form):
        errors = []
        for field_errors in form.errors.values():
            errors.extend(field_errors)
        self.request.session["confirm_errors"] = errors
        return redirect(self.request.path)

    def get(self, request, *args, **kwargs):
        errors = request.session.pop("confirm_errors", None)
        response = super().get(request, *args, **kwargs)
        response.context_data["session_errors"] = errors
        return response