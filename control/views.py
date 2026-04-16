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
from .forms import RoleForm, UserForm


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
def roles_create(request):
    """Create a new role."""
    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Role \"{form.cleaned_data['name']}\" created successfully.")
            return redirect("control:roles_list")
    else:
        form = RoleForm()

    return render(request, "control/roles_form.html", {
        "form": form,
        "grouped_permissions": _grouped_permissions(),
        "page_action": "Create",
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
            return redirect("control:roles_list")
    else:
        form = RoleForm(instance=role)

    return render(request, "control/roles_form.html", {
        "form": form,
        "role": role,
        "grouped_permissions": _grouped_permissions(),
        "page_action": "Edit",
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
            user = form.save()
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
            form.save()
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
