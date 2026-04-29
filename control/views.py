"""
control/views.py
----------------
Views for the custom admin control panel.

All views in this module are protected by the @staff_required decorator.
They contain no business logic — data aggregation for display is kept
minimal and read-only here.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

import json
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Min, Max
from django.db.models.functions import TruncDay, TruncHour
from django.utils import timezone

from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken

from fidpha.models import Account, Contract, Contract_Product, Product, UserProfile, RoleProfile
from api.models import APIToken, APITokenUsageLog
from sales.models import Sale, SaleImport
from .decorators import staff_required, perm_required, superuser_required


def _log(user, obj, flag, message=""):
    """Write an entry to Django's admin LogEntry audit table."""
    LogEntry.objects.log_action(
        user_id=user.pk,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=obj.pk,
        object_repr=str(obj)[:200],
        action_flag=flag,
        change_message=message,
    )
from .forms import RoleForm, UserForm, AccountForm, ContractForm, ContractProductForm, ContractProductFormSet, ProductForm, TokenForm, SocialAppForm, SiteForm


@staff_required
def dashboard(request):
    """
    Render the control panel dashboard with high-level system statistics.

    Displays counts for accounts, contracts, products, users, and API tokens
    — each split into active vs total where applicable — so the admin gets
    an instant overview of system health on login.

    Args:
        request: The incoming HTTP request (staff user required).

    Returns:
        Rendered dashboard template with stats context.
    """
    stats = {
        "accounts_active": Account.objects.filter(status="active").count(),
        "accounts_total": Account.objects.count(),
        "contracts_active": Contract.objects.filter(status="active").count(),
        "contracts_total": Contract.objects.count(),
        "products_active": Product.objects.filter(status="active").count(),
        "products_total": Product.objects.count(),
        "users_total": User.objects.count(),
        "tokens_active": APIToken.objects.filter(is_active=True).count(),
        "tokens_total": APIToken.objects.count(),
    }

    recent_activity = (
        LogEntry.objects
        .select_related("user", "content_type")
        .exclude(change_message__startswith="[")
        .order_by("-action_time")[:25]
    )

    return render(request, "control/dashboard.html", {
        "stats": stats,
        "recent_activity": recent_activity,
        "ADDITION": ADDITION,
        "CHANGE": CHANGE,
        "DELETION": DELETION,
    })


# ---------------------------------------------------------------------------
# Roles (Django Groups)
# ---------------------------------------------------------------------------

# Available icons for roles — (material-icon-name, display-label)
_ROLE_ICONS = [
    ('manage_accounts',     'Accounts'),
    ('person_search',       'Users'),
    ('api',                 'API'),
    ('receipt_long',        'Contracts'),
    ('inventory_2',         'Inventory'),
    ('sync',                'Sync'),
    ('local_pharmacy',      'Pharmacy'),
    ('medication',          'Products'),
    ('analytics',           'Analytics'),
    ('security',            'Security'),
    ('admin_panel_settings','Admin'),
    ('support_agent',       'Support'),
    ('business',            'Business'),
    ('badge',               'General'),
    ('key',                 'Access'),
    ('bar_chart',           'Reports'),
    ('group',               'Team'),
    ('assignment',          'Tasks'),
]

# Human-readable labels for Django / third-party app labels
_APP_FRIENDLY: dict[str, str] = {
    "account":       "Allauth — Email & Login",
    "admin":         "Admin — Audit Log",
    "api":           "API — Tokens",
    "auth":          "Authentication — Users & Groups",
    "authtoken":     "REST Framework — Auth Tokens (internal)",
    "contenttypes":  "Django — Content Types (internal)",
    "fidpha":        "WinInPharma — Core Data",
    "sessions":      "Django — Sessions (internal)",
    "sites":         "Django — Sites",
    "socialaccount": "Allauth — Social OAuth (Google)",
}

# Human-readable labels for model names (lowercase, as stored in ContentType)
_MODEL_FRIENDLY: dict[str, str] = {
    # allauth.account
    "emailaddress":      "Email Addresses",
    "emailconfirmation": "Email Confirmations",
    # admin
    "logentry":          "Audit Log Entries",
    # api
    "apitoken":          "API Tokens",
    # auth
    "permission":        "Permissions",
    "group":             "Groups (Roles)",
    "user":              "Users",
    # authtoken
    "token":             "DRF Auth Tokens",
    "tokenproxy":        "DRF Auth Token Proxy",
    # contenttypes
    "contenttype":       "Content Types",
    # fidpha
    "account":           "Pharmacy Accounts",
    "contract":          "Contracts",
    "contract_product":  "Contract ↔ Product Links",
    "product":           "Products",
    "userprofile":       "User Profiles (Portal)",
    # sessions
    "session":           "Sessions",
    # sites
    "site":              "Sites",
    # socialaccount
    "socialaccount":     "Social Accounts (OAuth)",
    "socialapp":         "Social Applications (e.g. Google)",
    "socialtoken":       "Social OAuth Tokens",
}


def _grouped_permissions() -> list[dict]:
    """
    Return all permissions grouped by app label, ready for the template.

    Each entry in the returned list is a dict:
        {
            "app_label":    str,   # raw app label
            "app_friendly": str,   # human-readable app label
            "models": [
                {
                    "model":          str,   # raw model name
                    "model_friendly": str,   # human-readable model name
                    "permissions":    list,
                }
            ]
        }

    Friendly names are looked up from _APP_FRIENDLY / _MODEL_FRIENDLY;
    unknown labels fall back to a capitalised version of the raw name.
    """
    apps: dict[str, dict[str, list]] = {}
    perms = (
        Permission.objects
        .select_related("content_type")
        .order_by("content_type__app_label", "content_type__model", "codename")
    )
    for perm in perms:
        ct = perm.content_type
        apps.setdefault(ct.app_label, {}).setdefault(ct.model, []).append(perm)

    grouped = []
    for app_label, models in sorted(apps.items()):
        model_list = [
            {
                "model":          model,
                "model_friendly": _MODEL_FRIENDLY.get(model, model.replace("_", " ").title()),
                "permissions":    perms_list,
            }
            for model, perms_list in sorted(models.items())
        ]
        grouped.append({
            "app_label":    app_label,
            "app_friendly": _APP_FRIENDLY.get(app_label, app_label.title()),
            "models":       model_list,
        })
    return grouped


@perm_required('auth.view_group')
def roles_list(request):
    """List all roles with name, permission count, and user count."""
    roles = (
        Group.objects
        .select_related('profile')
        .annotate(perm_count=Count("permissions", distinct=True),
                  user_count=Count("user", distinct=True))
        .order_by("name")
    )
    return render(request, "control/roles_list.html", {"roles": roles})


@perm_required('auth.view_group')
def roles_detail(request, pk: int):
    """Read-only detail view for a role."""
    role = get_object_or_404(
        Group.objects.select_related('profile').prefetch_related("permissions__content_type", "user_set"),
        pk=pk,
    )
    # Group permissions by app label for display
    perm_groups: dict[str, list] = {}
    for perm in role.permissions.all():
        label = _APP_FRIENDLY.get(perm.content_type.app_label,
                                  perm.content_type.app_label.title())
        perm_groups.setdefault(label, []).append(perm)
    perm_groups_sorted = sorted(perm_groups.items())

    return render(request, "control/roles_detail.html", {
        "role": role,
        "perm_groups": perm_groups_sorted,
        "assigned_users": role.user_set.order_by("username"),
    })


@perm_required('auth.add_group')
def roles_create(request):
    """Create a new role. Supports ?clone=pk to pre-fill from an existing role."""
    clone_perm_ids = set()
    current_icon   = 'badge'

    if request.method == "POST":
        current_icon = request.POST.get('role_icon', 'badge')
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save()
            RoleProfile.objects.update_or_create(group=role, defaults={'icon': current_icon})
            _log(request.user, role, ADDITION)
            messages.success(request, f"Role \"{role.name}\" created successfully.")
            return redirect("control:roles_list")
    else:
        form = RoleForm()
        clone_pk = request.GET.get("clone")
        if clone_pk:
            try:
                src = Group.objects.select_related('profile').prefetch_related("permissions").get(pk=clone_pk)
                form.fields["name"].initial = f"Copy of {src.name}"
                clone_perm_ids = set(src.permissions.values_list("pk", flat=True))
                current_icon = getattr(getattr(src, 'profile', None), 'icon', 'badge')
            except Group.DoesNotExist:
                pass

    return render(request, "control/roles_form.html", {
        "form":               form,
        "grouped_permissions": _grouped_permissions(),
        "page_action":        "Create",
        "clone_perm_ids":     clone_perm_ids,
        "current_icon":       current_icon,
        "role_icons":         _ROLE_ICONS,
    })


@perm_required('auth.change_group')
def roles_edit(request, pk: int):
    """Edit an existing role."""
    role = get_object_or_404(Group.objects.select_related('profile'), pk=pk)

    if request.method == "POST":
        submitted_icon = request.POST.get('role_icon', 'badge')
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            RoleProfile.objects.update_or_create(group=role, defaults={'icon': submitted_icon})
            _log(request.user, role, CHANGE)
            messages.success(request, f"Role \"{role.name}\" updated successfully.")
            return redirect("control:roles_detail", pk=role.pk)
        request.session["_role_edit_err"] = {
            "name":           list(form.errors.get("name", [])),
            "submitted_name": request.POST.get("name", ""),
            "submitted_icon": submitted_icon,
        }
        return redirect(request.path)

    stored = request.session.pop("_role_edit_err", None)
    form = RoleForm(instance=role)
    if stored and stored.get("submitted_name") is not None:
        form.initial["name"] = stored["submitted_name"]
    name_errors  = stored["name"] if stored else []
    current_icon = (stored or {}).get("submitted_icon") or getattr(getattr(role, 'profile', None), 'icon', 'badge')

    return render(request, "control/roles_form.html", {
        "form":               form,
        "role":               role,
        "grouped_permissions": _grouped_permissions(),
        "page_action":        "Edit",
        "name_errors":        name_errors,
        "current_icon":       current_icon,
        "role_icons":         _ROLE_ICONS,
    })


@perm_required('auth.delete_group')
def roles_delete(request, pk: int):
    """Delete a role after confirmation."""
    role = get_object_or_404(Group, pk=pk)
    user_count = role.user_set.count()

    if request.method == "POST":
        name = role.name
        _log(request.user, role, DELETION)
        role.delete()
        messages.success(request, f"Role \"{name}\" deleted.")
        return redirect("control:roles_list")

    return render(request, "control/roles_confirm_delete.html", {
        "role": role,
        "user_count": user_count,
    })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _user_type(user: User) -> str:
    """Return a string label for the user's type."""
    if user.is_superuser:
        return "superuser"
    if user.is_staff:
        return "staff"
    return "portal"


@perm_required('auth.view_user')
def users_list(request):
    """
    List users split into two blocks: Admin users (staff/superusers)
    and Portal users (non-staff). Both blocks are filtered client-side
    in the template — no search GET params needed.
    """
    admin_users = (
        User.objects
        .filter(is_staff=True)
        .prefetch_related("groups")
        .order_by("-is_superuser", "username")
    )
    portal_users = (
        User.objects
        .filter(is_staff=False)
        .select_related("profile__account")
        .order_by("username")
    )
    return render(request, "control/users_list.html", {
        "admin_users":  admin_users,
        "portal_users": portal_users,
    })


@perm_required('auth.add_user')
def users_create(request):
    """Create a new user. Supports ?clone=pk to pre-fill from an existing user."""
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save(actor=request.user)
            _log(request.user, user, ADDITION)
            messages.success(request, f"User \"{user.username}\" created successfully.")
            return redirect("control:users_detail", pk=user.pk)

        selected_type       = request.POST.get("user_type", "portal")
        selected_role_pk    = request.POST.get("role", "")
        selected_account_pk = request.POST.get("account", "")
    else:
        form = UserForm()
        selected_type = "portal"
        selected_role_pk = ""
        selected_account_pk = ""

        # Pre-fill from ?account=pk&type=portal (e.g. launched from account edit page)
        preset_account = request.GET.get("account")
        preset_type    = request.GET.get("type")
        if preset_account and not request.GET.get("clone"):
            try:
                acc = Account.objects.get(pk=preset_account)
                selected_account_pk = acc.pk
                form.fields["account"].initial = acc.pk
            except Account.DoesNotExist:
                pass
        if preset_type in ("portal", "staff", "superuser") and not request.GET.get("clone"):
            selected_type = preset_type
            form.fields["user_type"].initial = preset_type

        # Clone: pre-fill from existing user
        clone_pk = request.GET.get("clone")
        if clone_pk:
            try:
                src = (
                    User.objects
                    .select_related("profile__account")
                    .prefetch_related("groups")
                    .get(pk=clone_pk)
                )
                form.fields["first_name"].initial = src.first_name
                form.fields["last_name"].initial  = src.last_name
                form.fields["email"].initial      = src.email
                form.fields["is_active"].initial  = src.is_active
                if src.is_superuser:
                    selected_type = "superuser"
                    form.fields["user_type"].initial = "superuser"
                elif src.is_staff:
                    selected_type = "staff"
                    form.fields["user_type"].initial = "staff"
                    first_group = src.groups.first()
                    if first_group:
                        selected_role_pk = first_group.pk
                        form.fields["role"].initial = first_group.pk
                else:
                    selected_type = "portal"
                    form.fields["user_type"].initial = "portal"
                    try:
                        selected_account_pk = src.profile.account_id or ""
                        form.fields["account"].initial = selected_account_pk
                    except Exception:
                        pass
            except User.DoesNotExist:
                pass

    return render(request, "control/users_form.html", {
        "form":               form,
        "page_action":        "Create",
        "roles":              Group.objects.order_by("name"),
        "accounts":           Account.objects.order_by("name"),
        "selected_type":      selected_type,
        "selected_role_pk":   selected_role_pk,
        "selected_account_pk": selected_account_pk,
    })


@perm_required('auth.view_user')
def users_detail(request, pk: int):
    """Read-only detail view for a user."""
    user = get_object_or_404(
        User.objects
        .select_related("profile__account")
        .prefetch_related("groups__permissions"),
        pk=pk,
    )
    utype   = _user_type(user)
    profile = getattr(user, "profile", None)
    social_accounts = (
        SocialAccount.objects
        .filter(user=user)
        .prefetch_related("socialtoken_set__app")
        .order_by("provider")
    )

    ctx = {
        "u":               user,
        "utype":           utype,
        "profile":         profile,
        "social_accounts": social_accounts,
    }

    return render(request, "control/users_detail.html", ctx)


@perm_required('auth.change_user')
def users_edit(request, pk: int):
    """Edit an existing user."""
    user = get_object_or_404(
        User.objects
        .select_related("profile__account")
        .prefetch_related("groups"),
        pk=pk,
    )

    if request.method == "POST":
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save(actor=request.user)
            _log(request.user, user, CHANGE)
            messages.success(request, f"User \"{user.username}\" updated successfully.")
            return redirect("control:users_detail", pk=user.pk)

        selected_type       = request.POST.get("user_type", "portal")
        selected_role_pk    = request.POST.get("role", "")
        selected_account_pk = request.POST.get("account", "")
    else:
        form = UserForm(instance=user)
        selected_type = _user_type(user)
        first_group = user.groups.first()
        selected_role_pk = first_group.pk if first_group else ""
        profile = getattr(user, "profile", None)
        selected_account_pk = (profile.account_id if profile and profile.account_id else "") or ""

    profile = getattr(user, "profile", None)

    return render(request, "control/users_form.html", {
        "form":               form,
        "user_obj":           user,
        "utype":              _user_type(user),
        "profile":            profile,
        "page_action":        "Edit",
        "roles":              Group.objects.order_by("name"),
        "accounts":           Account.objects.order_by("name"),
        "selected_type":      selected_type,
        "selected_role_pk":   selected_role_pk,
        "selected_account_pk": selected_account_pk,
    })


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@perm_required('fidpha.view_account')
def accounts_list(request):
    """List all accounts with annotated contract and user counts."""
    accounts = (
        Account.objects
        .annotate(
            contract_count=Count("contracts", distinct=True),
            user_count=Count("users", distinct=True),
        )
        .order_by("name")
    )
    return render(request, "control/accounts_list.html", {"accounts": accounts})


@perm_required('fidpha.add_account')
def accounts_create(request):
    """Create a new account. Supports ?clone=pk to pre-fill from an existing account."""
    if request.method == "POST":
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.created_by = request.user
            account.save()
            _log(request.user, account, ADDITION)
            messages.success(request, f'Account "{account.name}" created successfully.')
            return redirect("control:accounts_detail", pk=account.pk)
        # PRG: store submitted data so a page reload won't re-POST
        request.session["_account_create_form"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        return redirect(request.path)

    stored = request.session.pop("_account_create_form", None)
    if stored:
        form = AccountForm(stored)
        form.is_valid()
    else:
        form = AccountForm()
        clone_pk = request.GET.get("clone")
        if clone_pk:
            try:
                src = Account.objects.get(pk=clone_pk)
                form.initial = {
                    "name":            f"Copy of {src.name}",
                    "city":            src.city,
                    "location":        src.location,
                    "phone":           src.phone,
                    "email":           src.email,
                    "pharmacy_portal": src.pharmacy_portal,
                    "status":          src.status,
                }
            except Account.DoesNotExist:
                pass

    return render(request, "control/accounts_form.html", {
        "form":        form,
        "page_action": "Create",
    })


@perm_required('fidpha.view_account')
def accounts_detail(request, pk: int):
    """Read-only detail view for an account."""
    account = get_object_or_404(
        Account.objects.prefetch_related("contracts", "users__user"),
        pk=pk,
    )
    active_contract    = (account.contracts
                          .filter(status="active")
                          .annotate(product_count=Count("products", distinct=True))
                          .first())
    inactive_contracts = (account.contracts
                          .filter(status="inactive")
                          .annotate(product_count=Count("products", distinct=True))
                          .order_by("-end_date"))
    contract_count     = account.contracts.count()

    return render(request, "control/accounts_detail.html", {
        "account":            account,
        "active_contract":    active_contract,
        "inactive_contracts": inactive_contracts,
        "contract_count":     contract_count,
        "portal_users":       account.users.select_related("user").order_by("user__username"),
    })


@perm_required('fidpha.change_account')
def accounts_edit(request, pk: int):
    """Edit an existing account."""
    account = get_object_or_404(Account, pk=pk)

    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            account = form.save(commit=False)
            account.modified_by = request.user
            account.save()
            _log(request.user, account, CHANGE)
            messages.success(request, f'Account "{account.name}" updated successfully.')
            return redirect("control:accounts_detail", pk=account.pk)
        request.session["_account_edit_form"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        return redirect(request.path)

    stored = request.session.pop("_account_edit_form", None)
    if stored:
        form = AccountForm(stored, instance=account)
        form.is_valid()
    else:
        form = AccountForm(instance=account)

    active_contract    = (account.contracts
                          .filter(status="active")
                          .annotate(product_count=Count("products", distinct=True))
                          .first())
    inactive_contracts = (account.contracts
                          .exclude(status="active")
                          .annotate(product_count=Count("products", distinct=True))
                          .order_by("-end_date"))
    contract_count     = account.contracts.count()
    portal_users       = account.users.select_related("user").order_by("user__username")

    return render(request, "control/accounts_form.html", {
        "form":               form,
        "account":            account,
        "page_action":        "Edit",
        "active_contract":    active_contract,
        "inactive_contracts": inactive_contracts,
        "contract_count":     contract_count,
        "portal_users":       portal_users,
    })


@perm_required('fidpha.delete_account')
def accounts_delete(request, pk: int):
    """Delete an account after confirmation."""
    account = get_object_or_404(Account, pk=pk)
    contract_count        = account.contracts.count()
    active_contract_count = account.contracts.filter(status="active").count()
    user_count            = account.users.count()

    if request.method == "POST":
        name = account.name
        _log(request.user, account, DELETION)
        account.delete()
        messages.success(request, f'Account "{name}" deleted.')
        return redirect("control:accounts_list")

    return render(request, "control/accounts_confirm_delete.html", {
        "account":              account,
        "contract_count":       contract_count,
        "active_contract_count": active_contract_count,
        "user_count":           user_count,
    })


@perm_required('auth.delete_user')
def users_delete(request, pk: int):
    """Delete a user after confirmation."""
    user = get_object_or_404(User.objects.select_related("profile__account"), pk=pk)
    utype = _user_type(user)
    profile = getattr(user, "profile", None)

    if request.method == "POST":
        username = user.username
        _log(request.user, user, DELETION)
        user.delete()
        messages.success(request, f"User \"{username}\" deleted.")
        return redirect("control:users_list")

    return render(request, "control/users_confirm_delete.html", {
        "u": user,
        "utype": utype,
        "profile": profile,
    })


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

_CP_PREFIX = "cp"  # formset prefix used consistently across all contract views


def _duration_str(start, end) -> str:
    """Return a human-readable duration string, e.g. '2 months, 5 days'."""
    if not start or not end:
        return ""
    total_days = (end.date() - start.date()).days
    if total_days < 0:
        return ""
    if total_days == 0:
        return "Same day"
    years, rem = divmod(total_days, 365)
    months, days = divmod(rem, 30)
    parts = []
    if years:  parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months: parts.append(f"{months} month{'s' if months > 1 else ''}")
    if days:   parts.append(f"{days} day{'s' if days > 1 else ''}")
    return ", ".join(parts)


def _available_products(contract=None):
    """
    Products available to add to a contract.
    - Active contract (or new): only active products.
    - Inactive contract: all products (active + inactive), so staff can pre-link
      a product before both are activated together.
    Already-linked products for the given contract are excluded (they show via
    the existing formset rows).
    """
    allow_inactive = contract is not None and contract.status == "inactive"
    qs = Product.objects.all() if allow_inactive else Product.objects.filter(status="active")
    if contract:
        linked = Contract_Product.objects.filter(contract=contract).values_list("product_id", flat=True)
        qs = qs.exclude(pk__in=linked)
    return qs.order_by("designation")


def _patch_freed_product_queryset(formset, available, data):
    """
    When a product row is deleted and re-added in the same submission, the product
    is still 'linked' in the DB so extra forms' querysets would reject it.
    Extend those querysets to include the freed products.
    """
    freed_pks = {
        f.instance.product_id
        for f in formset.initial_forms
        if data.get(f"{f.prefix}-DELETE") and f.instance.product_id
    }
    if freed_pks:
        freed_qs = Product.objects.filter(pk__in=freed_pks, status="active")
        extended  = (available | freed_qs).distinct()
        for f in formset.extra_forms:
            f.fields["product"].queryset = extended.order_by("designation")


@perm_required('fidpha.view_contract')
def contracts_list(request):
    """List all contracts with account, status, product count, and sync state."""
    contracts = (
        Contract.objects
        .select_related("account")
        .annotate(product_count=Count("products", distinct=True))
        .order_by("-status", "account__name", "title")
    )
    return render(request, "control/contracts_list.html", {"contracts": contracts})


@perm_required('fidpha.view_contract')
def contracts_detail(request, pk: int):
    """Read-only detail view: contract info, product list, and monthly/daily trend chart."""
    import datetime
    import calendar as cal
    from django.db.models import Sum, ExpressionWrapper, FloatField, Count as DbCount
    from django.db.models.functions import Round, TruncMonth, TruncDay, TruncYear

    contract = get_object_or_404(
        Contract.objects.select_related("account"),
        pk=pk,
    )

    contract_products = list(
        Contract_Product.objects
        .filter(contract=contract)
        .select_related("product")
        .order_by("product__designation")
    )

    sale_count = Sale.objects.filter(contract_product__contract=contract).count()

    def _pts_qs():
        return Sale.objects.filter(
            contract_product__contract=contract,
            status=Sale.STATUS_ACCEPTED,
            product_ppv__isnull=False,
        ).annotate(pts=Round(ExpressionWrapper(
            F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
            output_field=FloatField(),
        )))

    # Per-product breakdown for the products table
    cp_pts_agg = {
        r["contract_product_id"]: int(r["total_pts"] or 0)
        for r in _pts_qs()
        .values("contract_product_id")
        .annotate(total_pts=Sum("pts"))
    }
    cp_units_agg = {
        r["contract_product_id"]: int(r["total"] or 0)
        for r in Sale.objects.filter(
            contract_product__contract=contract,
            status=Sale.STATUS_ACCEPTED,
        ).values("contract_product_id").annotate(total=Sum("quantity"))
    }

    products_data = []
    for cp in contract_products:
        products_data.append({
            "cp":        cp,
            "units_sold": cp_units_agg.get(cp.pk, 0),
            "points":     cp_pts_agg.get(cp.pk, 0),
        })

    # ── Chart: available years ──
    now = timezone.now()
    year_rows = (
        _pts_qs()
        .annotate(yr=TruncYear("sale_datetime"))
        .values_list("yr", flat=True)
        .distinct()
        .order_by("yr")
    )
    available_years = sorted({dt.year for dt in year_rows if dt})

    # ── Per-year monthly data ──
    years_monthly = {}
    for yr in available_years:
        yr_months = [datetime.datetime(yr, m, 1, tzinfo=datetime.timezone.utc) for m in range(1, 13)]
        yr_mqs = (
            _pts_qs()
            .filter(sale_datetime__year=yr)
            .annotate(month=TruncMonth("sale_datetime"))
            .values("month")
            .annotate(total=Sum("pts"), unique_products=DbCount("contract_product__product", distinct=True))
        )
        mmap = {r["month"].strftime("%Y-%m"): r for r in yr_mqs}
        years_monthly[str(yr)] = {
            "keys":   [d.strftime("%Y-%m") for d in yr_months],
            "labels": [d.strftime("%b") for d in yr_months],
            "pts":    [int(mmap.get(d.strftime("%Y-%m"), {}).get("total") or 0) for d in yr_months],
            "prods":  [mmap.get(d.strftime("%Y-%m"), {}).get("unique_products") or 0 for d in yr_months],
        }

    # ── Last-12-months monthly data (default view) ──
    month_dates = []
    for i in range(11, -1, -1):
        m, y = now.month - i, now.year
        while m <= 0:
            m += 12
            y -= 1
        month_dates.append(datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc))

    last12_keys   = [d.strftime("%Y-%m") for d in month_dates]
    last12_labels = [d.strftime("%b %Y") for d in month_dates]
    l12_mqs = (
        _pts_qs()
        .filter(sale_datetime__gte=month_dates[0])
        .annotate(month=TruncMonth("sale_datetime"))
        .values("month")
        .annotate(total=Sum("pts"), unique_products=DbCount("contract_product__product", distinct=True))
    )
    l12_map       = {r["month"].strftime("%Y-%m"): r for r in l12_mqs}
    last12_pts    = [int(l12_map.get(k, {}).get("total") or 0) for k in last12_keys]
    last12_prods  = [l12_map.get(k, {}).get("unique_products") or 0 for k in last12_keys]

    years_monthly["last12"] = {
        "keys":   last12_keys,
        "labels": last12_labels,
        "pts":    last12_pts,
        "prods":  last12_prods,
    }

    # ── Product chart data (full contract totals) ──
    products_sorted      = sorted(products_data, key=lambda d: d["points"], reverse=True)
    product_chart_labels = [d["cp"].product.designation for d in products_sorted]
    product_chart_data   = [d["points"] for d in products_sorted]

    # ── Products by month (for cross-chart filtering) ──
    products_by_month = {}
    prod_month_qs = (
        _pts_qs()
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

    # ── Daily drill-down data (all months with data) ──
    daily_by_month = {}
    daily_qs = (
        _pts_qs()
        .annotate(day=TruncDay("sale_datetime"))
        .values("day")
        .annotate(total=Sum("pts"), unique_products=DbCount("contract_product__product", distinct=True))
        .order_by("day")
    )
    for r in daily_qs:
        mk    = r["day"].strftime("%Y-%m")
        d_int = r["day"].day
        if mk not in daily_by_month:
            yr_d, mo_d = int(mk[:4]), int(mk[5:7])
            num_days = cal.monthrange(yr_d, mo_d)[1]
            daily_by_month[mk] = {
                "labels": list(range(1, num_days + 1)),
                "pts":    [0] * num_days,
                "prods":  [0] * num_days,
            }
        daily_by_month[mk]["pts"][d_int - 1]   = int(r["total"] or 0)
        daily_by_month[mk]["prods"][d_int - 1] = r["unique_products"] or 0

    return render(request, "control/contracts_detail.html", {
        "contract":          contract,
        "contract_products": contract_products,
        "products_data":     products_data,
        "sale_count":        sale_count,
        "duration":          _duration_str(contract.start_date, contract.end_date),
        "available_years":   json.dumps(available_years),
        "years_monthly":          json.dumps(years_monthly),
        "daily_by_month":         json.dumps(daily_by_month),
        "products_by_month":      json.dumps(products_by_month),
        "product_chart_labels":   json.dumps(product_chart_labels),
        "product_chart_data":     json.dumps(product_chart_data),
    })


@perm_required('fidpha.add_contract')
def contracts_create(request):
    """Create a new contract. Supports ?account=pk (preset) and ?clone=pk."""
    from django.forms import inlineformset_factory  # needed for dynamic clone formset
    available = _available_products()
    fkwargs   = {"available_products": available}

    if request.method == "POST":
        form    = ContractForm(request.POST)
        formset = ContractProductFormSet(request.POST, prefix=_CP_PREFIX, form_kwargs=fkwargs)
        if form.is_valid() and formset.is_valid():
            contract = form.save(commit=False)
            contract.created_by  = request.user
            contract.modified_by = request.user  # on first save, modifier = creator
            contract.save()
            formset.instance = contract
            formset.save()
            _log(request.user, contract, ADDITION)
            messages.success(request, f'Contract "{contract.title}" created successfully.')
            return redirect("control:contracts_detail", pk=contract.pk)
        request.session["_contract_create_form"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        return redirect(request.path)

    stored    = request.session.pop("_contract_create_form", None)
    clone_pk  = request.GET.get("clone")
    preset_pk = request.GET.get("account")

    if stored:
        form    = ContractForm(stored)
        formset = ContractProductFormSet(stored, prefix=_CP_PREFIX, form_kwargs=fkwargs)
        form.is_valid()
        formset.is_valid()

    elif clone_pk:
        try:
            src = Contract.objects.prefetch_related("contract_product_set__product").get(pk=clone_pk)
            form = ContractForm(initial={
                "title":       f"Copy of {src.title}",
                "designation": src.designation,
                "account":     src.account_id,
                "status":      src.status,
            })
            initial_products = [
                {"product": cp.product_id, "external_designation": cp.external_designation}
                for cp in src.contract_product_set.select_related("product").order_by("product__designation")
            ]
            n_extra  = max(1, len(initial_products))
            CloneSet = inlineformset_factory(
                Contract, Contract_Product, form=ContractProductForm,
                extra=n_extra, can_delete=True, min_num=0, validate_min=False,
            )
            formset = CloneSet(initial=initial_products, prefix=_CP_PREFIX, form_kwargs=fkwargs)
        except Contract.DoesNotExist:
            form    = ContractForm()
            formset = ContractProductFormSet(prefix=_CP_PREFIX, form_kwargs=fkwargs)

    else:
        initial = {}
        if preset_pk:
            try:
                initial["account"] = Account.objects.get(pk=preset_pk)
            except Account.DoesNotExist:
                pass
        form    = ContractForm(initial=initial)
        formset = ContractProductFormSet(prefix=_CP_PREFIX, form_kwargs=fkwargs)

    return render(request, "control/contracts_form.html", {
        "form":          form,
        "formset":       formset,
        "page_action":   "Create",
        "cp_prefix":     _CP_PREFIX,
        "products_json": json.dumps([
            {"id": p.pk, "label": p.designation, "active": p.status == "active"}
            for p in Product.objects.order_by("designation")
        ]),
    })


@perm_required('fidpha.change_contract')
def contracts_edit(request, pk: int):
    """Edit an existing contract and manage its product lines."""
    contract  = get_object_or_404(Contract, pk=pk)
    available = _available_products(contract=contract)
    fkwargs   = {"available_products": available}

    if request.method == "POST":
        form    = ContractForm(request.POST, instance=contract)
        formset = ContractProductFormSet(request.POST, instance=contract, prefix=_CP_PREFIX, form_kwargs=fkwargs)
        _patch_freed_product_queryset(formset, available, request.POST)
        if form.is_valid() and formset.is_valid():
            contract = form.save(commit=False)
            contract.modified_by = request.user
            contract.save()
            formset.save()
            _log(request.user, contract, CHANGE)
            messages.success(request, f'Contract "{contract.title}" updated successfully.')
            return redirect("control:contracts_detail", pk=contract.pk)
        request.session[f"_contract_edit_form_{pk}"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        return redirect(request.path)

    stored = request.session.pop(f"_contract_edit_form_{pk}", None)
    if stored:
        form    = ContractForm(stored, instance=contract)
        formset = ContractProductFormSet(stored, instance=contract, prefix=_CP_PREFIX, form_kwargs=fkwargs)
        form.is_valid()
        _patch_freed_product_queryset(formset, available, stored)
        formset.is_valid()
    else:
        form    = ContractForm(instance=contract)
        formset = ContractProductFormSet(instance=contract, prefix=_CP_PREFIX, form_kwargs=fkwargs)

    return render(request, "control/contracts_form.html", {
        "form":          form,
        "formset":       formset,
        "contract":      contract,
        "page_action":   "Edit",
        "cp_prefix":     _CP_PREFIX,
        "products_json": json.dumps([
            {"id": p.pk, "label": p.designation, "active": p.status == "active"}
            for p in Product.objects.order_by("designation")
        ]),
    })


@perm_required('fidpha.delete_contract')
def contracts_delete(request, pk: int):
    """Delete a contract after confirmation. Blocked if sales records exist."""
    contract      = get_object_or_404(Contract.objects.select_related("account"), pk=pk)
    product_count = Contract_Product.objects.filter(contract=contract).count()
    sale_count    = Sale.objects.filter(contract_product__contract=contract).count()
    has_sales     = sale_count > 0

    if request.method == "POST":
        if has_sales:
            messages.error(request, "Cannot delete: this contract has sales records.")
            return redirect("control:contracts_detail", pk=contract.pk)
        title = contract.title
        _log(request.user, contract, DELETION)
        contract.delete()
        messages.success(request, f'Contract "{title}" deleted.')
        return redirect("control:contracts_list")

    return render(request, "control/contracts_confirm_delete.html", {
        "contract":      contract,
        "product_count": product_count,
        "sale_count":    sale_count,
        "has_sales":     has_sales,
    })


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@perm_required('fidpha.view_product')
def products_list(request):
    products = (
        Product.objects
        .annotate(contract_count=Count("contracts", distinct=True))
        .order_by("designation")
    )
    return render(request, "control/products_list.html", {"products": products})


@perm_required('fidpha.view_product')
def products_detail(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    contract_products = (
        Contract_Product.objects
        .filter(product=product)
        .select_related('contract__account')
        .order_by('-contract__status', 'contract__account__name')
    )
    return render(request, "control/products_detail.html", {
        "product": product,
        "contract_products": contract_products,
    })


@perm_required('fidpha.add_product')
def products_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by  = request.user
            product.modified_by = request.user
            product.save()
            _log(request.user, product, ADDITION)
            messages.success(request, f'Product "{product.designation}" created successfully.')
            return redirect("control:products_list")
        request.session["_product_create_form"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        return redirect(request.path)

    stored   = request.session.pop("_product_create_form", None)
    clone_pk = request.GET.get("clone")

    if stored:
        form = ProductForm(stored)
        form.is_valid()
    elif clone_pk:
        try:
            src  = Product.objects.get(pk=clone_pk)
            form = ProductForm(initial={
                "designation": f"Copy of {src.designation}",
                "status":      src.status,
                # code left blank — must be unique, user must provide one
            })
        except Product.DoesNotExist:
            src  = None
            form = ProductForm()
    else:
        src  = None
        form = ProductForm()

    return render(request, "control/products_form.html", {
        "form":         form,
        "page_action":  "Create",
        "cloned_from":  src if clone_pk else None,
    })


@perm_required('fidpha.change_product')
def products_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save(commit=False)
            product.modified_by = request.user
            product.save()
            _log(request.user, product, CHANGE)
            messages.success(request, f'Product "{product.designation}" updated successfully.')
            return redirect("control:products_list")
        request.session[f"_product_edit_form_{pk}"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        return redirect(request.path)

    stored = request.session.pop(f"_product_edit_form_{pk}", None)
    if stored:
        form = ProductForm(stored, instance=product)
        form.is_valid()
    else:
        form = ProductForm(instance=product)

    return render(request, "control/products_form.html", {
        "form": form, "product": product, "page_action": "Edit",
    })


@perm_required('fidpha.delete_product')
def products_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    contract_count        = Contract_Product.objects.filter(product=product).count()
    active_contract_count = Contract_Product.objects.filter(
        product=product, contract__status="active"
    ).count()

    if request.method == "POST":
        name = product.designation
        _log(request.user, product, DELETION)
        product.delete()
        messages.success(request, f'Product "{name}" deleted.')
        return redirect("control:products_list")

    return render(request, "control/products_confirm_delete.html", {
        "product":              product,
        "contract_count":       contract_count,
        "active_contract_count": active_contract_count,
    })


# ---------------------------------------------------------------------------
# API Tokens
# ---------------------------------------------------------------------------

@perm_required('api.view_apitoken')
def tokens_list(request):
    tokens          = APIToken.objects.select_related("created_by").order_by("-created_at")
    new_token_value = request.session.pop("_new_token_value", None)
    return render(request, "control/tokens_list.html", {
        "tokens":          tokens,
        "new_token_value": new_token_value,
    })


@perm_required('api.view_apitoken')
def tokens_detail(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)

    if request.method == "POST":
        new_name = request.POST.get("name", "").strip()
        if new_name:
            token.name = new_name
            token.save(update_fields=["name"])
            _log(request.user, token, CHANGE, "Renamed")
            messages.success(request, "Token name updated.")
        return redirect("control:tokens_detail", pk=pk)

    today  = timezone.now().date()

    # 30-day daily buckets (reused for 7-day slice)
    days_30 = [today - timedelta(days=i) for i in range(29, -1, -1)]
    logs_30 = (
        APITokenUsageLog.objects
        .filter(token=token, called_at__date__gte=days_30[0])
        .annotate(day=TruncDay("called_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    counts_30 = {}
    for row in logs_30:
        if row["day"]:
            counts_30[row["day"].date()] = row["count"]

    chart_30_labels = [d.strftime("%d %b") for d in days_30]
    chart_30_data   = [counts_30.get(d, 0) for d in days_30]
    chart_7_labels  = chart_30_labels[-7:]
    chart_7_data    = chart_30_data[-7:]

    # Today by hour
    logs_today = (
        APITokenUsageLog.objects
        .filter(token=token, called_at__date=today)
        .annotate(hr=TruncHour("called_at"))
        .values("hr")
        .annotate(count=Count("id"))
    )
    counts_today = {}
    for row in logs_today:
        if row["hr"]:
            counts_today[row["hr"].hour] = row["count"]
    chart_today_labels = [f"{h:02d}:00" for h in range(24)]
    chart_today_data   = [counts_today.get(h, 0) for h in range(24)]
    total_today        = sum(chart_today_data)

    recent_logs = APITokenUsageLog.objects.filter(token=token)[:50]

    return render(request, "control/tokens_detail.html", {
        "token":              token,
        "chart_30_labels":    json.dumps(chart_30_labels),
        "chart_30_data":      json.dumps(chart_30_data),
        "chart_7_labels":     json.dumps(chart_7_labels),
        "chart_7_data":       json.dumps(chart_7_data),
        "chart_today_labels": json.dumps(chart_today_labels),
        "chart_today_data":   json.dumps(chart_today_data),
        "recent_logs":        recent_logs,
        "total_today":        total_today,
    })


@perm_required('api.add_apitoken')
def tokens_create(request):
    if request.method == "POST":
        form = TokenForm(request.POST)
        if form.is_valid():
            token = form.save(commit=False)
            token.created_by = request.user
            token.save()
            _log(request.user, token, ADDITION)
            request.session["_new_token_value"] = token.raw_token
            messages.success(request, f'Token "{token.name}" created.')
            return redirect("control:tokens_list")
    else:
        form = TokenForm()

    return render(request, "control/tokens_form.html", {"form": form})


@perm_required('api.change_apitoken')
def tokens_revoke(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)
    if request.method == "POST":
        token.is_active = False
        token.save(update_fields=["is_active"])
        _log(request.user, token, CHANGE, "Revoked")
        messages.success(request, f'Token "{token.name}" revoked.')
    return redirect("control:tokens_list")


@perm_required('api.change_apitoken')
def tokens_reactivate(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)
    if request.method == "POST":
        token.is_active = True
        token.save(update_fields=["is_active"])
        _log(request.user, token, CHANGE, "Reactivated")
        messages.success(request, f'Token "{token.name}" reactivated.')
    return redirect("control:tokens_list")


@perm_required('api.delete_apitoken')
def tokens_delete(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)

    if request.method == "POST":
        name = token.name
        _log(request.user, token, DELETION)
        token.delete()
        messages.success(request, f'Token "{name}" deleted.')
        return redirect("control:tokens_list")

    return render(request, "control/tokens_confirm_delete.html", {"token": token})


# ===========================================================================
# Configuration — Social Accounts
# ===========================================================================

@superuser_required
def social_accounts_list(request):
    accounts = (
        SocialAccount.objects
        .select_related("user")
        .prefetch_related("socialtoken_set__app")
        .order_by("provider", "user__username")
    )
    return render(request, "control/social_accounts_list.html", {"accounts": accounts})


@superuser_required
def social_account_unlink(request, pk: int):
    sa = get_object_or_404(SocialAccount, pk=pk)
    user_pk = sa.user_id
    if request.method == "POST":
        username = sa.user.username
        provider = sa.provider
        sa.delete()
        messages.success(request, f'Unlinked {provider.title()} account from "{username}".')
    return redirect("control:users_detail", pk=user_pk)


# ===========================================================================
# Configuration — Social Applications
# ===========================================================================

@superuser_required
def social_apps_list(request):
    apps = SocialApp.objects.prefetch_related("sites").order_by("provider", "name")
    return render(request, "control/social_apps_list.html", {"apps": apps})


@superuser_required
def social_apps_detail(request, pk: int):
    app = get_object_or_404(SocialApp.objects.prefetch_related("sites"), pk=pk)
    token_count = SocialToken.objects.filter(app=app).count()
    return render(request, "control/social_apps_detail.html", {
        "app": app,
        "token_count": token_count,
    })


@superuser_required
def social_apps_create(request):
    if request.method == "POST":
        form = SocialAppForm(request.POST)
        if form.is_valid():
            app = form.save()
            messages.success(request, f'Social application "{app.name}" created.')
            return redirect("control:social_apps_detail", pk=app.pk)
    else:
        form = SocialAppForm()
    return render(request, "control/social_apps_form.html", {
        "form": form, "page_action": "Create",
    })


@superuser_required
def social_apps_edit(request, pk: int):
    app = get_object_or_404(SocialApp, pk=pk)
    if request.method == "POST":
        form = SocialAppForm(request.POST, instance=app)
        if form.is_valid():
            form.save()
            messages.success(request, f'Social application "{app.name}" updated.')
            return redirect("control:social_apps_detail", pk=app.pk)
    else:
        form = SocialAppForm(instance=app)
    return render(request, "control/social_apps_form.html", {
        "form": form, "page_action": "Edit", "app": app,
    })


@superuser_required
def social_apps_delete(request, pk: int):
    app = get_object_or_404(SocialApp, pk=pk)
    if request.method == "POST":
        name = app.name
        app.delete()
        messages.success(request, f'Social application "{name}" deleted.')
        return redirect("control:social_apps_list")
    return render(request, "control/social_apps_confirm_delete.html", {"app": app})


# ===========================================================================
# Configuration — Sites
# ===========================================================================

@superuser_required
def site_edit(request):
    site = Site.objects.first()
    if not site:
        site = Site.objects.create(domain="example.com", name="WinInPharma")
    if request.method == "POST":
        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            messages.success(request, "Site configuration updated.")
            return redirect("control:site_edit")
    else:
        form = SiteForm(instance=site)
    return render(request, "control/site_edit.html", {"form": form, "site": site})


# ===========================================================================
# Sales Review
# ===========================================================================

@perm_required('sales.view_sale')
def sales_list(request):
    """Sales review page — batch list with inline expansion."""
    accounts = Account.objects.order_by("name")
    return render(request, "control/sales_list.html", {
        "accounts":      accounts,
        "init_account":  request.GET.get("account",  ""),
        "init_contract": request.GET.get("contract", ""),
    })


@perm_required('sales.view_sale')
def sales_api_batches_v2(request):
    """
    Paginated batch list built from the Sale table (review perspective).
    Fully system-rejected batches (no Sale records) are excluded — they live
    in the sync import log.
    Status chips / filter reflect Sale review status, not SaleImport validation.
    Filter params: date_from, date_to (received_at), account, contract, status, q (batch ID).
    """
    from django.http import JsonResponse

    date_from   = request.GET.get("date_from",  "").strip()
    date_to     = request.GET.get("date_to",    "").strip()
    account_pk  = request.GET.get("account",    "").strip()
    contract_pk = request.GET.get("contract",   "").strip()
    status_f    = request.GET.get("status",     "").strip()
    batch_q     = request.GET.get("q",          "").strip()
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 25

    qs = Sale.objects.values("sale_import__batch_id", "sale_import__account_code")

    if date_from:
        qs = qs.filter(sale_import__received_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_import__received_at__date__lte=date_to)
    if account_pk:
        try:
            acc_obj = Account.objects.get(pk=account_pk)
            qs = qs.filter(sale_import__account_code=acc_obj.code)
        except Account.DoesNotExist:
            pass
    if contract_pk:
        qs = qs.filter(contract_product__contract_id=contract_pk)
    if batch_q:
        qs = qs.filter(sale_import__batch_id__icontains=batch_q)

    qs = qs.annotate(
        received_at  =Min("sale_import__received_at"),
        total        =Count("pk"),
        pending      =Count("pk", filter=Q(status=Sale.STATUS_PENDING)),
        accepted     =Count("pk", filter=Q(status=Sale.STATUS_ACCEPTED)),
        rejected     =Count("pk", filter=Q(status=Sale.STATUS_REJECTED)),
        ppv_mismatch  =Count(
            "pk",
            filter=Q(contract_product__product__ppv__isnull=False)
                   & ~Q(ppv=F("contract_product__product__ppv")),
        ),
        sale_date_min =Min("sale_datetime"),
        sale_date_max =Max("sale_datetime"),
    )

    if status_f == "pending":
        qs = qs.filter(pending__gt=0)
    elif status_f == "accepted":
        qs = qs.filter(accepted__gt=0)
    elif status_f == "rejected":
        qs = qs.filter(rejected__gt=0)

    qs = qs.order_by("-received_at", "sale_import__batch_id")

    total_count = qs.count()
    offset      = (page - 1) * per_page
    page_rows   = list(qs[offset : offset + per_page])

    account_codes = {b["sale_import__account_code"] for b in page_rows}
    batch_ids     = {b["sale_import__batch_id"]     for b in page_rows}

    account_map = {
        a.code: {"name": a.name, "pk": a.pk, "city": a.city or "", "code": a.code}
        for a in Account.objects.filter(code__in=account_codes)
    }

    contract_map = {}
    if batch_ids:
        for row in (
            Sale.objects
            .filter(sale_import__batch_id__in=batch_ids)
            .values(
                "sale_import__batch_id",
                "contract_product__contract_id",
                "contract_product__contract__title",
            )
            .distinct()
        ):
            bid = row["sale_import__batch_id"]
            if bid not in contract_map:
                contract_map[bid] = {
                    "pk":    row["contract_product__contract_id"],
                    "title": row["contract_product__contract__title"],
                }

    result = []
    for b in page_rows:
        acc = account_map.get(b["sale_import__account_code"], {})
        ct  = contract_map.get(b["sale_import__batch_id"], {})
        result.append({
            "batch_id":       b["sale_import__batch_id"],
            "account_code":   b["sale_import__account_code"],
            "account_name":   acc.get("name", b["sale_import__account_code"]),
            "account_pk":     acc.get("pk"),
            "account_city":   acc.get("city", ""),
            "contract_pk":    ct.get("pk"),
            "contract_title": ct.get("title"),
            "received_at":     b["received_at"].strftime("%d %b %Y, %H:%M") if b["received_at"] else None,
            "received_at_iso": b["received_at"].isoformat()                 if b["received_at"] else None,
            "received_date":   b["received_at"].strftime("%Y-%m-%d")        if b["received_at"] else None,
            "total":           b["total"],
            "pending":         b["pending"],
            "accepted":        b["accepted"],
            "rejected":        b["rejected"],
            "ppv_mismatch":    b["ppv_mismatch"],
            "sale_date_min":   b["sale_date_min"].strftime("%Y-%m-%dT%H:%M:%S") if b["sale_date_min"] else None,
            "sale_date_max":   b["sale_date_max"].strftime("%Y-%m-%dT%H:%M:%S") if b["sale_date_max"] else None,
        })

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return JsonResponse({
        "batches":  result,
        "total":    total_count,
        "page":     page,
        "pages":    total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    })


@perm_required('sales.view_sale')
def sales_api_contracts(request):
    from django.http import JsonResponse
    account_pk = request.GET.get("account", "")
    if not account_pk:
        return JsonResponse({"contracts": []})
    qs = Contract.objects.filter(account_id=account_pk).order_by("-start_date")
    data = []
    for c in qs:
        data.append({
            "pk":         c.pk,
            "title":      c.title,
            "status":     c.status,
            "start_date": c.start_date.strftime("%d %b %Y"),
            "end_date":   c.end_date.strftime("%d %b %Y"),
            "sale_count": Sale.objects.filter(contract_product__contract=c).count(),
        })
    return JsonResponse({"contracts": data})


@perm_required('sales.view_sale')
def sales_api_batches(request):
    from django.http import JsonResponse
    contract_pk = request.GET.get("contract", "")
    if not contract_pk:
        return JsonResponse({"batches": []})
    rows = (
        Sale.objects
        .filter(contract_product__contract_id=contract_pk)
        .values("sale_import__batch_id")
        .annotate(
            total=Count("id"),
            pending=Count("id",  filter=Q(status=Sale.STATUS_PENDING)),
            accepted=Count("id", filter=Q(status=Sale.STATUS_ACCEPTED)),
            rejected=Count("id", filter=Q(status=Sale.STATUS_REJECTED)),
            first_date=Min("sale_datetime"),
            last_date=Max("sale_datetime"),
        )
        .order_by("-last_date", "sale_import__batch_id")
    )
    return JsonResponse({"batches": [
        {
            "batch_id":  r["sale_import__batch_id"],
            "total":     r["total"],
            "pending":   r["pending"],
            "accepted":  r["accepted"],
            "rejected":  r["rejected"],
            "last_date":      r["last_date"].strftime("%d %b %Y")   if r["last_date"]  else None,
            "first_date_iso": r["first_date"].strftime("%Y-%m-%d") if r["first_date"] else None,
            "last_date_iso":  r["last_date"].strftime("%Y-%m-%d")  if r["last_date"]  else None,
        }
        for r in rows
    ]})


@perm_required('sales.view_sale')
def sales_api_sales(request):
    from django.http import JsonResponse
    contract_pk = request.GET.get("contract", "")
    batch_id    = request.GET.get("batch", "").strip()
    if not contract_pk or not batch_id:
        return JsonResponse({"sales": [], "counts": {"pending": 0, "accepted": 0, "rejected": 0}})
    qs = (
        Sale.objects
        .filter(
            contract_product__contract_id=contract_pk,
            sale_import__batch_id=batch_id,
        )
        .select_related("contract_product__product", "sale_import", "reviewed_by")
        .order_by("sale_datetime")
    )
    data   = []
    counts = {"pending": 0, "accepted": 0, "rejected": 0}
    for s in qs:
        contract_ppv = s.contract_product.product.ppv
        factor       = s.contract_product.points_per_unit
        points       = round(float(contract_ppv) * float(factor) * s.quantity) if contract_ppv else 0
        ppv_mismatch = (contract_ppv is not None and s.ppv != contract_ppv)
        data.append({
            "pk":               s.pk,
            "product":          s.contract_product.product.designation,
            "ext_designation":  s.sale_import.external_designation,
            "sale_datetime":    s.sale_datetime.strftime("%d %b %Y, %H:%M"),
            "sale_datetime_iso": s.sale_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            "quantity":         s.quantity,
            "ppv":              str(s.ppv) if s.ppv else "—",
            "contract_ppv":     str(contract_ppv) if contract_ppv else None,
            "ppv_mismatch":     ppv_mismatch,
            "points":           points,
            "status":           s.status,
            "reviewed_by":      (
                s.reviewed_by.get_full_name() or s.reviewed_by.username
                if s.reviewed_by else None
            ),
            "reviewed_at":      s.reviewed_at.strftime("%d %b %Y, %H:%M") if s.reviewed_at else None,
        })
        counts[s.status] = counts.get(s.status, 0) + 1
    return JsonResponse({"sales": data, "counts": counts})


@perm_required('sales.view_sale')
def sales_export_csv(request):
    import csv
    from django.http import StreamingHttpResponse
    contract_pk = request.GET.get("contract", "")
    batch_id    = request.GET.get("batch", "").strip()
    if not contract_pk:
        return redirect("control:sales_list")
    qs = (
        Sale.objects
        .filter(contract_product__contract_id=contract_pk)
        .select_related("contract_product__product", "sale_import", "reviewed_by")
        .order_by("sale_import__batch_id", "sale_datetime")
    )
    if batch_id:
        qs = qs.filter(sale_import__batch_id=batch_id)

    def generate_rows():
        yield ["Batch ID", "Product", "External Designation", "Sale Date",
               "Qty", "PPV", "Contract PPV", "PPV OK", "Points",
               "Status", "Reviewed By", "Reviewed At"]
        for s in qs.iterator():
            cp           = s.contract_product
            contract_ppv = s.product_ppv
            ppv_ok       = contract_ppv is None or s.ppv == contract_ppv
            points       = round(float(contract_ppv) * float(cp.points_per_unit) * s.quantity) if contract_ppv else 0
            reviewed_by  = (
                (s.reviewed_by.get_full_name() or s.reviewed_by.username)
                if s.reviewed_by else ""
            )
            yield [
                s.sale_import.batch_id if s.sale_import else "",
                cp.product.designation,
                s.sale_import.external_designation if s.sale_import else "",
                s.sale_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                s.quantity,
                str(s.ppv),
                str(contract_ppv) if contract_ppv else "",
                "yes" if ppv_ok else "NO",
                points,
                s.status,
                reviewed_by,
                s.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if s.reviewed_at else "",
            ]

    class _Echo:
        def write(self, value): return value

    writer = csv.writer(_Echo())
    ts     = timezone.now().strftime("%Y%m%d_%H%M")
    fname  = f"sales_{contract_pk}{'_' + batch_id if batch_id else ''}_{ts}.csv"
    response = StreamingHttpResponse(
        (writer.writerow(r) for r in generate_rows()),
        content_type="text/csv",
    )
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response


@perm_required('sales.view_sale')
def sales_export_list_csv(request):
    """Export all Sale records matching the batch-list filters as CSV."""
    import csv
    from django.http import StreamingHttpResponse

    date_from   = request.GET.get("date_from",  "").strip()
    date_to     = request.GET.get("date_to",    "").strip()
    account_pk  = request.GET.get("account",    "").strip()
    contract_pk = request.GET.get("contract",   "").strip()
    status_f    = request.GET.get("status",     "").strip()
    batch_q     = request.GET.get("q",          "").strip()

    qs = (
        Sale.objects
        .select_related(
            "contract_product__product",
            "contract_product__contract__account",
            "sale_import",
            "reviewed_by",
        )
        .order_by("sale_import__batch_id", "sale_datetime")
    )

    if date_from:
        qs = qs.filter(sale_import__received_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_import__received_at__date__lte=date_to)
    if account_pk:
        try:
            acc_obj = Account.objects.get(pk=account_pk)
            qs = qs.filter(sale_import__account_code=acc_obj.code)
        except Account.DoesNotExist:
            pass
    if contract_pk:
        qs = qs.filter(contract_product__contract_id=contract_pk)
    if batch_q:
        qs = qs.filter(sale_import__batch_id__icontains=batch_q)
    if status_f in (Sale.STATUS_PENDING, Sale.STATUS_ACCEPTED, Sale.STATUS_REJECTED):
        qs = qs.filter(status=status_f)

    def generate_rows():
        yield ["Batch ID", "Account", "Contract", "Product", "External Designation",
               "Sale Date", "Qty", "PPV", "Contract PPV", "PPV OK", "Points",
               "Status", "Reviewed By", "Reviewed At"]
        for s in qs.iterator():
            cp           = s.contract_product
            contract_ppv = s.product_ppv
            ppv_ok       = contract_ppv is None or s.ppv == contract_ppv
            points       = round(float(contract_ppv) * float(cp.points_per_unit) * s.quantity) if contract_ppv else 0
            reviewed_by  = (
                (s.reviewed_by.get_full_name() or s.reviewed_by.username)
                if s.reviewed_by else ""
            )
            yield [
                s.sale_import.batch_id if s.sale_import else "",
                cp.contract.account.name if cp.contract and cp.contract.account else "",
                cp.contract.title if cp.contract else "",
                cp.product.designation,
                s.sale_import.external_designation if s.sale_import else "",
                s.sale_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                s.quantity,
                str(s.ppv),
                str(contract_ppv) if contract_ppv else "",
                "yes" if ppv_ok else "NO",
                points,
                s.status,
                reviewed_by,
                s.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if s.reviewed_at else "",
            ]

    class _Echo:
        def write(self, value): return value

    writer   = csv.writer(_Echo())
    response = StreamingHttpResponse(
        (writer.writerow(r) for r in generate_rows()),
        content_type="text/csv",
    )
    ts = timezone.now().strftime("%Y%m%d_%H%M")
    response["Content-Disposition"] = f'attachment; filename="sales_export_{ts}.csv"'
    return response


def _sales_redirect(request):
    """Rebuild the ?account=&contract=&batch= return URL after an accept/reject action."""
    from django.urls import reverse
    params = []
    for key in ("account", "contract", "batch"):
        v = request.POST.get(key) or request.GET.get(key)
        if v:
            params.append(f"{key}={v}")
    base = reverse("control:sales_list")
    return redirect(base + ("?" + "&".join(params) if params else ""))


@perm_required('sales.change_sale')
def sale_accept(request, pk):
    if request.method != "POST":
        return redirect("control:sales_list")
    sale = get_object_or_404(Sale, pk=pk)
    sale.status      = Sale.STATUS_ACCEPTED
    sale.reviewed_by = request.user
    sale.reviewed_at = timezone.now()
    sale.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return _sales_redirect(request)


@perm_required('sales.change_sale')
def sale_reject(request, pk):
    if request.method != "POST":
        return redirect("control:sales_list")
    sale = get_object_or_404(Sale, pk=pk)
    sale.status      = Sale.STATUS_REJECTED
    sale.reviewed_by = request.user
    sale.reviewed_at = timezone.now()
    sale.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return _sales_redirect(request)


@perm_required('sales.change_sale')
def sales_bulk_accept(request):
    """Accept all pending sales in the selected contract+batch."""
    if request.method != "POST":
        return redirect("control:sales_list")
    contract_pk = request.POST.get("contract")
    batch_id    = request.POST.get("batch", "").strip()
    if contract_pk and batch_id:
        Sale.objects.filter(
            contract_product__contract_id=contract_pk,
            sale_import__batch_id=batch_id,
            status=Sale.STATUS_PENDING,
        ).update(
            status=Sale.STATUS_ACCEPTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
    return _sales_redirect(request)


@perm_required('sales.change_sale')
def sales_bulk_update(request):
    """AJAX: accept or reject a specific list of sale PKs."""
    from django.http import JsonResponse
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)
    raw_pks = request.POST.get("pks", "")
    status  = request.POST.get("status", "")
    pks     = [int(p) for p in raw_pks.split(",") if p.strip().isdigit()]
    if status not in (Sale.STATUS_ACCEPTED, Sale.STATUS_REJECTED) or not pks:
        return JsonResponse({"ok": False, "error": "Invalid request"}, status=400)
    Sale.objects.filter(pk__in=pks).update(
        status=status,
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
    )
    return JsonResponse({"ok": True, "updated": len(pks)})


# ===========================================================================
# Sync Import Log  (superuser debug tool)
# ===========================================================================

@superuser_required
def sync_log(request):
    import csv
    from django.http import StreamingHttpResponse
    from django.db.models import Count, Exists, Max, OuterRef, Q
    from fidpha.models import Contract as _Contract

    # Filters
    status_filter   = request.GET.get("status", "")
    batch_filter    = request.GET.get("batch", "").strip()
    account_filter  = request.GET.get("account", "").strip()
    date_from       = request.GET.get("date_from", "")
    date_to         = request.GET.get("date_to", "")
    sale_date_from  = request.GET.get("sale_date_from", "")
    sale_date_to    = request.GET.get("sale_date_to", "")
    contract_filter = request.GET.get("contract_id", "")
    token_filter    = request.GET.get("token_id", "")
    reason_filter   = request.GET.get("reason", "").strip()

    filtered_qs = SaleImport.objects.all()
    if status_filter:
        filtered_qs = filtered_qs.filter(status=status_filter)
    if batch_filter:
        filtered_qs = filtered_qs.filter(batch_id__icontains=batch_filter)
    if account_filter:
        filtered_qs = filtered_qs.filter(account_code__icontains=account_filter)
    if date_from:
        filtered_qs = filtered_qs.filter(received_at__date__gte=date_from)
    if date_to:
        filtered_qs = filtered_qs.filter(received_at__date__lte=date_to)
    if sale_date_from:
        filtered_qs = filtered_qs.filter(sale_datetime__date__gte=sale_date_from)
    if sale_date_to:
        filtered_qs = filtered_qs.filter(sale_datetime__date__lte=sale_date_to)
    if contract_filter:
        filtered_qs = filtered_qs.filter(contract_product__contract_id=contract_filter)
    if token_filter:
        filtered_qs = filtered_qs.filter(token_id=token_filter)
    if reason_filter:
        filtered_qs = filtered_qs.filter(rejection_reason__icontains=reason_filter)

    # CSV export — stream all matching rows, bypassing pagination
    if request.GET.get("export") == "csv":
        export_qs = (
            filtered_qs
            .select_related("token", "inserted_by", "contract_product__contract")
            .order_by("-received_at", "-pk")
        )

        def generate_rows():
            yield ["Batch ID", "Received At", "Sale Date", "Account Code", "Contract",
                   "Designation", "Qty", "PPV", "Status", "Rejection Reason", "Source"]
            for r in export_qs.iterator():
                contract_title = ""
                if r.contract_product and r.contract_product.contract:
                    contract_title = r.contract_product.contract.title
                source = r.token.name if r.token else (r.inserted_by.username if r.inserted_by else "")
                yield [
                    r.batch_id,
                    r.received_at.strftime("%Y-%m-%d %H:%M:%S"),
                    r.sale_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    r.account_code,
                    contract_title,
                    r.external_designation,
                    r.quantity,
                    r.ppv,
                    r.status,
                    r.rejection_reason,
                    source,
                ]

        class _Echo:
            def write(self, value): return value

        writer = csv.writer(_Echo())
        response = StreamingHttpResponse(
            (writer.writerow(r) for r in generate_rows()),
            content_type="text/csv",
        )
        response["Content-Disposition"] = 'attachment; filename="sync_import_log.csv"'
        return response

    total = filtered_qs.count()

    # Dropdown options for filters
    all_contracts = list(_Contract.objects.order_by("title").values("pk", "title"))
    all_tokens    = list(APIToken.objects.order_by("name").values("pk", "name"))

    any_filter = any([
        status_filter, batch_filter, account_filter, date_from, date_to,
        sale_date_from, sale_date_to, contract_filter, token_filter, reason_filter,
    ])

    # Paginate by distinct batch_id (10 batches per page)
    batch_qs = (
        filtered_qs
        .values("batch_id")
        .annotate(latest=Max("received_at"))
        .order_by("-latest")
    )
    batch_paginator = Paginator(batch_qs, 10)
    batch_page      = batch_paginator.get_page(request.GET.get("page"))
    current_ids     = [b["batch_id"] for b in batch_page.object_list]

    # Fetch filtered rows for this page's batches
    page_rows = []
    batch_stats = {}
    if current_ids:
        page_rows = list(
            filtered_qs
            .filter(batch_id__in=current_ids)
            .select_related("token", "inserted_by", "contract_product__contract")
            .annotate(
                has_sale=Exists(Sale.objects.filter(sale_import=OuterRef("pk"))),
            )
            .order_by("-received_at", "-pk")
        )
        for b in (
            SaleImport.objects
            .filter(batch_id__in=current_ids)
            .values("batch_id")
            .annotate(
                total=Count("pk"),
                n_accepted=Count("pk", filter=Q(status=SaleImport.STATUS_ACCEPTED)),
                n_rejected=Count("pk", filter=Q(status=SaleImport.STATUS_REJECTED)),
                n_pending=Count("pk", filter=Q(status=SaleImport.STATUS_PENDING)),
            )
        ):
            batch_stats[b["batch_id"]] = b

    rows_by_batch = {}
    for row in page_rows:
        rows_by_batch.setdefault(row.batch_id, []).append(row)

    groups = [
        {
            "batch_id": b["batch_id"],
            "rows":     rows_by_batch.get(b["batch_id"], []),
            "stats":    batch_stats.get(b["batch_id"], {}),
        }
        for b in batch_page.object_list
    ]

    query = request.GET.copy()
    query.pop("page", None)
    query.pop("export", None)

    return render(request, "control/sync_log.html", {
        "groups":           groups,
        "page_obj":         batch_page,
        "total":            total,
        "total_batches":    batch_paginator.count,
        "status_filter":    status_filter,
        "batch_filter":     batch_filter,
        "account_filter":   account_filter,
        "date_from":        date_from,
        "date_to":          date_to,
        "sale_date_from":   sale_date_from,
        "sale_date_to":     sale_date_to,
        "contract_filter":  contract_filter,
        "token_filter":     token_filter,
        "reason_filter":    reason_filter,
        "all_contracts":    all_contracts,
        "all_tokens":       all_tokens,
        "any_filter":       any_filter,
        "query_string":     query.urlencode(),
        "STATUS_PENDING":   SaleImport.STATUS_PENDING,
        "STATUS_ACCEPTED":  SaleImport.STATUS_ACCEPTED,
        "STATUS_REJECTED":  SaleImport.STATUS_REJECTED,
    })
