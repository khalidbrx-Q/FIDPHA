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
from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncHour
from django.utils import timezone

from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken

from fidpha.models import Account, Contract, Contract_Product, Product, UserProfile, RoleProfile
from api.models import APIToken, APITokenUsageLog
from sales.models import Sale, SaleImport
from .decorators import staff_required
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

    return render(request, "control/dashboard.html", {"stats": stats})


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
    "fidpha":        "FIDPHA — Core Data",
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


@staff_required
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


@staff_required
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


@staff_required
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


@staff_required
def roles_edit(request, pk: int):
    """Edit an existing role."""
    role = get_object_or_404(Group.objects.select_related('profile'), pk=pk)

    if request.method == "POST":
        submitted_icon = request.POST.get('role_icon', 'badge')
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            RoleProfile.objects.update_or_create(group=role, defaults={'icon': submitted_icon})
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


@staff_required
def roles_delete(request, pk: int):
    """Delete a role after confirmation."""
    role = get_object_or_404(Group, pk=pk)
    user_count = role.user_set.count()

    if request.method == "POST":
        name = role.name
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


@staff_required
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


@staff_required
def users_create(request):
    """Create a new user. Supports ?clone=pk to pre-fill from an existing user."""
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save(actor=request.user)
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


@staff_required
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

    return render(request, "control/users_detail.html", {
        "u":               user,
        "utype":           utype,
        "profile":         profile,
        "social_accounts": social_accounts,
    })


@staff_required
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

@staff_required
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


@staff_required
def accounts_create(request):
    """Create a new account. Supports ?clone=pk to pre-fill from an existing account."""
    if request.method == "POST":
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.created_by = request.user
            account.save()
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


@staff_required
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


@staff_required
def accounts_edit(request, pk: int):
    """Edit an existing account."""
    account = get_object_or_404(Account, pk=pk)

    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            account = form.save(commit=False)
            account.modified_by = request.user
            account.save()
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


@staff_required
def accounts_delete(request, pk: int):
    """Delete an account after confirmation."""
    account = get_object_or_404(Account, pk=pk)
    contract_count        = account.contracts.count()
    active_contract_count = account.contracts.filter(status="active").count()
    user_count            = account.users.count()

    if request.method == "POST":
        name = account.name
        account.delete()
        messages.success(request, f'Account "{name}" deleted.')
        return redirect("control:accounts_list")

    return render(request, "control/accounts_confirm_delete.html", {
        "account":              account,
        "contract_count":       contract_count,
        "active_contract_count": active_contract_count,
        "user_count":           user_count,
    })


@staff_required
def users_delete(request, pk: int):
    """Delete a user after confirmation."""
    user = get_object_or_404(User.objects.select_related("profile__account"), pk=pk)
    utype = _user_type(user)
    profile = getattr(user, "profile", None)

    if request.method == "POST":
        username = user.username
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


@staff_required
def contracts_list(request):
    """List all contracts with account, status, product count, and sync state."""
    contracts = (
        Contract.objects
        .select_related("account")
        .annotate(product_count=Count("products", distinct=True))
        .order_by("-status", "account__name", "title")
    )
    return render(request, "control/contracts_list.html", {"contracts": contracts})


@staff_required
def contracts_detail(request, pk: int):
    """Read-only detail view: contract info, product list, and sales sync stats."""
    contract = get_object_or_404(
        Contract.objects.select_related("account"),
        pk=pk,
    )
    contract_products = (
        Contract_Product.objects
        .filter(contract=contract)
        .select_related("product")
        .order_by("product__designation")
    )
    sale_count = Sale.objects.filter(contract_product__contract=contract).count()
    return render(request, "control/contracts_detail.html", {
        "contract":          contract,
        "contract_products": contract_products,
        "sale_count":        sale_count,
        "duration":          _duration_str(contract.start_date, contract.end_date),
    })


@staff_required
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


@staff_required
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


@staff_required
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

@staff_required
def products_list(request):
    products = (
        Product.objects
        .annotate(contract_count=Count("contracts", distinct=True))
        .order_by("designation")
    )
    return render(request, "control/products_list.html", {"products": products})


@staff_required
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


@staff_required
def products_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by  = request.user
            product.modified_by = request.user
            product.save()
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


@staff_required
def products_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save(commit=False)
            product.modified_by = request.user
            product.save()
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


@staff_required
def products_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    contract_count        = Contract_Product.objects.filter(product=product).count()
    active_contract_count = Contract_Product.objects.filter(
        product=product, contract__status="active"
    ).count()

    if request.method == "POST":
        name = product.designation
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

@staff_required
def tokens_list(request):
    tokens          = APIToken.objects.select_related("created_by").order_by("-created_at")
    new_token_value = request.session.pop("_new_token_value", None)
    return render(request, "control/tokens_list.html", {
        "tokens":          tokens,
        "new_token_value": new_token_value,
    })


@staff_required
def tokens_detail(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)

    if request.method == "POST":
        new_name = request.POST.get("name", "").strip()
        if new_name:
            token.name = new_name
            token.save(update_fields=["name"])
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


@staff_required
def tokens_create(request):
    if request.method == "POST":
        form = TokenForm(request.POST)
        if form.is_valid():
            token = form.save(commit=False)
            token.created_by = request.user
            token.save()
            request.session["_new_token_value"] = token.token
            messages.success(request, f'Token "{token.name}" created.')
            return redirect("control:tokens_list")
    else:
        form = TokenForm()

    return render(request, "control/tokens_form.html", {"form": form})


@staff_required
def tokens_revoke(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)
    if request.method == "POST":
        token.is_active = False
        token.save(update_fields=["is_active"])
        messages.success(request, f'Token "{token.name}" revoked.')
    return redirect("control:tokens_list")


@staff_required
def tokens_reactivate(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)
    if request.method == "POST":
        token.is_active = True
        token.save(update_fields=["is_active"])
        messages.success(request, f'Token "{token.name}" reactivated.')
    return redirect("control:tokens_list")


@staff_required
def tokens_delete(request, pk: int):
    token = get_object_or_404(APIToken, pk=pk)

    if request.method == "POST":
        name = token.name
        token.delete()
        messages.success(request, f'Token "{name}" deleted.')
        return redirect("control:tokens_list")

    return render(request, "control/tokens_confirm_delete.html", {"token": token})


# ===========================================================================
# Configuration — Social Accounts
# ===========================================================================

@staff_required
def social_accounts_list(request):
    accounts = (
        SocialAccount.objects
        .select_related("user")
        .prefetch_related("socialtoken_set__app")
        .order_by("provider", "user__username")
    )
    return render(request, "control/social_accounts_list.html", {"accounts": accounts})


@staff_required
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

@staff_required
def social_apps_list(request):
    apps = SocialApp.objects.prefetch_related("sites").order_by("provider", "name")
    return render(request, "control/social_apps_list.html", {"apps": apps})


@staff_required
def social_apps_detail(request, pk: int):
    app = get_object_or_404(SocialApp.objects.prefetch_related("sites"), pk=pk)
    token_count = SocialToken.objects.filter(app=app).count()
    return render(request, "control/social_apps_detail.html", {
        "app": app,
        "token_count": token_count,
    })


@staff_required
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


@staff_required
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


@staff_required
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

@staff_required
def site_edit(request):
    site = Site.objects.first()
    if not site:
        site = Site.objects.create(domain="example.com", name="FIDPHA")
    if request.method == "POST":
        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            messages.success(request, "Site configuration updated.")
            return redirect("control:site_edit")
    else:
        form = SiteForm(instance=site)
    return render(request, "control/site_edit.html", {"form": form, "site": site})
