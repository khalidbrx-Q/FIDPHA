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

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, Q

from fidpha.models import Account, Contract, Product, UserProfile
from api.models import APIToken
from .decorators import staff_required
from .forms import RoleForm, UserForm, AccountForm


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
        .annotate(perm_count=Count("permissions", distinct=True),
                  user_count=Count("user", distinct=True))
        .order_by("name")
    )
    return render(request, "control/roles_list.html", {"roles": roles})


@staff_required
def roles_detail(request, pk: int):
    """Read-only detail view for a role."""
    role = get_object_or_404(
        Group.objects.prefetch_related("permissions__content_type", "user_set"),
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

    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Role \"{form.cleaned_data['name']}\" created successfully.")
            return redirect("control:roles_list")
    else:
        form = RoleForm()
        clone_pk = request.GET.get("clone")
        if clone_pk:
            try:
                src = Group.objects.prefetch_related("permissions").get(pk=clone_pk)
                form.fields["name"].initial = f"Copy of {src.name}"
                clone_perm_ids = set(src.permissions.values_list("pk", flat=True))
            except Group.DoesNotExist:
                pass

    return render(request, "control/roles_form.html", {
        "form": form,
        "grouped_permissions": _grouped_permissions(),
        "page_action": "Create",
        "clone_perm_ids": clone_perm_ids,
    })


@staff_required
def roles_edit(request, pk: int):
    """Edit an existing role."""
    role = get_object_or_404(Group, pk=pk)

    if request.method == "POST":
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            messages.success(request, f"Role \"{role.name}\" updated successfully.")
            return redirect("control:roles_detail", pk=role.pk)
        # PRG: store errors in session and redirect back to GET so that
        # a page reload doesn't trigger the "resubmit?" browser dialog.
        request.session["_role_edit_err"] = {
            "name":           list(form.errors.get("name", [])),
            "submitted_name": request.POST.get("name", ""),
        }
        return redirect(request.path)

    # Pick up any validation errors stored by the previous POST
    stored = request.session.pop("_role_edit_err", None)
    form = RoleForm(instance=role)
    if stored and stored.get("submitted_name") is not None:
        # Override the form's initial so the input shows what the user typed
        form.initial["name"] = stored["submitted_name"]
    name_errors = stored["name"] if stored else []

    return render(request, "control/roles_form.html", {
        "form": form,
        "role": role,
        "grouped_permissions": _grouped_permissions(),
        "page_action": "Edit",
        "name_errors": name_errors,
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
    utype = _user_type(user)
    profile = getattr(user, "profile", None)

    return render(request, "control/users_detail.html", {
        "u": user,
        "utype": utype,
        "profile": profile,
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
