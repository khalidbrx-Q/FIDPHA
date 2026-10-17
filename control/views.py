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
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Min, Max
from django.db.models.functions import TruncDay, TruncHour
from django.utils import timezone
from django.utils.translation import gettext as _

from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken

from fidpha.models import Account, Contract, Contract_Product, Product, RoleProfile
from api.models import APIToken, APITokenUsageLog
from sales.models import Sale, SaleImport
from .decorators import staff_required, perm_required, superuser_required
from .forms import RoleForm, UserForm, AccountForm, ContractForm, ContractProductForm, ContractProductFormSet, ProductForm, TokenForm, SocialAppForm, SiteForm
from .models import SystemConfig


def _export_response(rows, basename, fmt):
    """Build a CSV / XLSX / JSON download response from a list of rows (first row = headers)."""
    import csv
    import io
    import json
    import zipfile
    from django.http import HttpResponse, StreamingHttpResponse

    headers = rows[0]
    data    = rows[1:]

    if fmt == "json":
        payload = [dict(zip(headers, row)) for row in data]
        resp = HttpResponse(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            content_type="application/json",
        )
        resp["Content-Disposition"] = f'attachment; filename="{basename}.json"'
        return resp

    if fmt == "xlsx":
        strings, strings_index = [], {}

        def si(s):
            s = str(s)
            if s not in strings_index:
                strings_index[s] = len(strings)
                strings.append(s)
            return strings_index[s]

        def xe(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        sheet_rows_xml = []
        from decimal import Decimal as _Dec
        for r_idx, row in enumerate(rows, 1):
            cells = []
            for c_idx, val in enumerate(row):
                col = chr(ord('A') + c_idx)
                ref = f"{col}{r_idx}"
                if isinstance(val, (int, float, _Dec)) and not isinstance(val, bool):
                    cells.append(f'<c r="{ref}"><v>{float(val)}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="s"><v>{si(str(val))}</v></c>')
            sheet_rows_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                '</Types>'
            ))
            zf.writestr("_rels/.rels", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>'
            ))
            zf.writestr("xl/workbook.xml", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>'
            ))
            zf.writestr("xl/_rels/workbook.xml.rels", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '</Relationships>'
            ))
            zf.writestr("xl/worksheets/sheet1.xml", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
                '</worksheet>'
            ))
            ss = "".join(f'<si><t xml:space="preserve">{xe(s)}</t></si>' for s in strings)
            zf.writestr("xl/sharedStrings.xml", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" uniqueCount="{len(strings)}">{ss}</sst>'
            ))
            zf.writestr("xl/styles.xml", (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<fonts><font/></fonts><fills><fill/></fills><borders><border/></borders>'
                '<cellStyleXfs><xf/></cellStyleXfs><cellXfs><xf/></cellXfs>'
                '</styleSheet>'
            ))
        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{basename}.xlsx"'
        return resp

    # default: csv
    class Echo:
        def write(self, value): return value

    writer = csv.writer(Echo())
    resp = StreamingHttpResponse(
        (writer.writerow(row) for row in rows),
        content_type="text/csv",
    )
    resp["Content-Disposition"] = f'attachment; filename="{basename}.csv"'
    return resp


def _log(user, obj, flag, message=""):
    """Write an entry to Django's admin LogEntry audit table.

    Uses `log_actions()` (the post-Django-5.1 API). `log_action()` is deprecated
    and removed in Django 6. `log_actions()` derives content_type / object_id /
    object_repr from the object itself.
    """
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[obj],
        action_flag=flag,
        change_message=message,
        single_object=True,
    )


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
        "accounts_active": Account.objects.filter(status=Account.STATUS_ACTIVE).count(),
        "accounts_total": Account.objects.count(),
        "contracts_active": Contract.objects.filter(status=Contract.STATUS_ACTIVE).count(),
        "contracts_total": Contract.objects.count(),
        "products_active": Product.objects.filter(status=Product.STATUS_ACTIVE).count(),
        "products_total": Product.objects.count(),
        "users_total": User.objects.count(),
        "tokens_active": APIToken.objects.filter(is_active=True).count(),
        "tokens_total": APIToken.objects.count(),
    }

    # Recent Activity is filtered by the viewer's view-permissions so a staff
    # user with limited access doesn't see audit entries on resources they
    # have no permission to view (information disclosure). Superusers see
    # everything (unchanged behaviour). Mirrors the sidebar's visibility rules.
    if request.user.is_superuser:
        activity_qs = LogEntry.objects.all()
    else:
        allowed_pairs: set[tuple[str, str]] = set()
        for perm in request.user.get_all_permissions():
            try:
                app_label, codename = perm.split(".", 1)
            except ValueError:
                continue
            if codename.startswith("view_"):
                allowed_pairs.add((app_label, codename[len("view_"):]))

        if not allowed_pairs:
            activity_qs = LogEntry.objects.none()
        else:
            perm_filter = Q()
            for app_label, model in allowed_pairs:
                perm_filter |= Q(
                    content_type__app_label=app_label,
                    content_type__model=model,
                )
            activity_qs = LogEntry.objects.filter(perm_filter)

    recent_activity = (
        activity_qs
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

# App labels excluded from the Roles permission form — framework internals or superuser-only
_EXCLUDED_APPS: frozenset[str] = frozenset({
    "authtoken",     # DRF token model — not used by this system
    "contenttypes",  # Django framework internal
    "sessions",      # Django framework internal
    "account",       # allauth email/login internals — not meaningful for staff
    "socialaccount", # OAuth management is superuser-only via settings pages
    "sites",         # site config is superuser-only via settings page
})

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
        .exclude(content_type__app_label__in=_EXCLUDED_APPS)
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
            rp, _ = RoleProfile.objects.update_or_create(group=role, defaults={'icon': current_icon})
            rp.created_by = request.user
            rp.modified_by = request.user
            rp.save()
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
            rp, _ = RoleProfile.objects.update_or_create(group=role, defaults={'icon': submitted_icon})
            rp.modified_by = request.user
            rp.save()
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
    user_ct = ContentType.objects.get_for_model(User)
    user_logs = (
        LogEntry.objects
        .filter(content_type=user_ct, object_id=str(user.pk))
        .select_related("user")
        .order_by("action_time")
    )
    creation_log    = user_logs.filter(action_flag=ADDITION).first()
    last_change_log = user_logs.filter(action_flag=CHANGE).last()

    ctx = {
        "u":               user,
        "utype":           utype,
        "profile":         profile,
        "social_accounts": social_accounts,
        "creation_log":    creation_log,
        "last_change_log": last_change_log,
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
        "form":               form,
        "page_action":        "Create",
        "global_auto_review": SystemConfig.get().auto_review_enabled,
    })


@perm_required('fidpha.view_account')
def accounts_detail(request, pk: int):
    """Read-only detail view for an account."""
    account = get_object_or_404(
        Account.objects.prefetch_related("contracts", "users__user"),
        pk=pk,
    )
    active_contract    = (account.contracts
                          .filter(status=Contract.STATUS_ACTIVE)
                          .annotate(product_count=Count("products", distinct=True))
                          .first())
    inactive_contracts = (account.contracts
                          .filter(status=Contract.STATUS_INACTIVE)
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
                          .filter(status=Contract.STATUS_ACTIVE)
                          .annotate(product_count=Count("products", distinct=True))
                          .first())
    inactive_contracts = (account.contracts
                          .exclude(status=Contract.STATUS_ACTIVE)
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
        "global_auto_review": SystemConfig.get().auto_review_enabled,
    })


@perm_required('fidpha.delete_account')
def accounts_delete(request, pk: int):
    """Delete an account after confirmation."""
    account = get_object_or_404(Account, pk=pk)
    contract_count        = account.contracts.count()
    active_contract_count = account.contracts.filter(status=Contract.STATUS_ACTIVE).count()
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
    if years:
        parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
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
    allow_inactive = contract is not None and contract.status == Contract.STATUS_INACTIVE
    qs = Product.objects.all() if allow_inactive else Product.objects.filter(status=Product.STATUS_ACTIVE)
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
        freed_qs = Product.objects.filter(pk__in=freed_pks, status=Product.STATUS_ACTIVE)
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
            {"id": p.pk, "label": p.designation, "active": p.status == Product.STATUS_ACTIVE, "code": p.code}
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
        # Tell contract.clean() which Contract_Product rows are being deleted so it
        # can exclude them from the inactive-product check (they're still in DB at
        # validation time, before formset.save() runs).
        total = int(request.POST.get(f"{_CP_PREFIX}-TOTAL_FORMS", 0))
        pending_deletes = set()
        for i in range(total):
            pk_raw  = request.POST.get(f"{_CP_PREFIX}-{i}-id", "")
            del_raw = request.POST.get(f"{_CP_PREFIX}-{i}-DELETE", "")
            if pk_raw and del_raw:
                try:
                    pending_deletes.add(int(pk_raw))
                except (ValueError, TypeError):
                    pass
        contract._pending_cp_deletes = pending_deletes
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
            {"id": p.pk, "label": p.designation, "active": p.status == Product.STATUS_ACTIVE, "code": p.code}
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


@perm_required('fidpha.change_contract')
def contracts_import_products(request, pk: int):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    contract = get_object_or_404(Contract, pk=pk)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        return JsonResponse({"error": "rows must be a list"}, status=400)

    from fidpha.services import bulk_link_products_to_contract
    result = bulk_link_products_to_contract(contract, rows, created_by=request.user)

    for cp in result["created"]:
        _log(request.user, cp, ADDITION, "bulk file import")

    return JsonResponse({
        "created": len(result["created"]),
        "skipped": [
            {
                "product_code":        s["row"].get("product_code", ""),
                "external_designation": s["row"].get("external_designation", ""),
                "points_per_unit":     s["row"].get("points_per_unit", ""),
                "target_quantity":     s["row"].get("target_quantity", ""),
                "reason":              s["reason"],
            }
            for s in result["skipped"]
        ],
    })


@perm_required('fidpha.change_contract')
def contracts_unlink_product(request, pk: int, cp_pk: int):
    """Immediately remove a single product link from a contract."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    contract = get_object_or_404(Contract, pk=pk)
    cp       = get_object_or_404(Contract_Product, pk=cp_pk, contract=contract)
    _log(request.user, cp, DELETION)
    cp.delete()
    return JsonResponse({'ok': True})


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
        product=product, contract__status=Contract.STATUS_ACTIVE
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


@perm_required('fidpha.view_product')
def products_export(request):
    fmt      = request.GET.get("format", "csv").lower()
    basename = f"products_{timezone.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    rows = [["code", "designation", "ppv", "status"]] + [
        [p.code, p.designation, p.ppv, p.status]
        for p in Product.objects.all().order_by("designation").iterator()
    ]
    return _export_response(rows, basename, fmt)


@perm_required('fidpha.view_account')
def accounts_export(request):
    fmt      = request.GET.get("format", "csv").lower()
    basename = f"accounts_{timezone.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    rows = [["code", "name", "city", "location", "phone", "email", "status", "pharmacy_portal", "auto_review_enabled"]] + [
        [a.code, a.name, a.city, a.location, a.phone, a.email, a.status,
         "yes" if a.pharmacy_portal else "no",
         "yes" if a.auto_review_enabled else "no"]
        for a in Account.objects.all().order_by("name").iterator()
    ]
    return _export_response(rows, basename, fmt)


@perm_required('fidpha.view_contract')
def contracts_export(request):
    fmt      = request.GET.get("format", "csv").lower()
    basename = f"contracts_{timezone.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    qs = (
        Contract.objects
        .select_related("account")
        .prefetch_related("contract_product_set__product")
        .order_by("-status", "account__name", "title")
    )
    headers = [
        "title", "account_code", "account_name", "start_date", "end_date", "status",
        "product_code", "product_designation", "product_ppv",
        "external_designation", "points_per_unit", "target_quantity",
    ]
    rows = [headers]
    for c in qs:
        contract_base = [
            c.title, c.account.code, c.account.name,
            c.start_date.strftime("%Y-%m-%d") if c.start_date else "",
            c.end_date.strftime("%Y-%m-%d")   if c.end_date   else "",
            c.status,
        ]
        cps = list(c.contract_product_set.all())
        if cps:
            for cp in cps:
                rows.append(contract_base + [
                    cp.product.code,
                    cp.product.designation,
                    cp.product.ppv,
                    cp.external_designation,
                    cp.points_per_unit,
                    cp.target_quantity if cp.target_quantity is not None else "",
                ])
        else:
            rows.append(contract_base + ["", "", "", "", "", ""])
    return _export_response(rows, basename, fmt)


@perm_required('fidpha.add_product')
def products_import(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        return JsonResponse({"error": "rows must be a list"}, status=400)

    from fidpha.services import bulk_import_products
    result = bulk_import_products(rows, created_by=request.user)

    for product in result["created"]:
        _log(request.user, product, ADDITION, "bulk CSV import")

    return JsonResponse({
        "created": len(result["created"]),
        "skipped": [
            {
                "code":        s["row"].get("code", ""),
                "designation": s["row"].get("designation", ""),
                "ppv":         s["row"].get("ppv", ""),
                "status":      s["row"].get("status", ""),
                "reason":      s["reason"],
            }
            for s in result["skipped"]
        ],
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
# Configuration — System
# ===========================================================================

@superuser_required
def system_settings(request):
    config = SystemConfig.get()
    errors = {}
    if request.method == "POST":
        # ── auto-review toggle ─────────────────────────────────────────────
        new_auto_review = request.POST.get("auto_review_enabled") == "1"
        if new_auto_review != config.auto_review_enabled:
            config.auto_review_updated_by = request.user  # stamp only on actual change
        config.auto_review_enabled = new_auto_review

        # ── ingestion limits ───────────────────────────────────────────────
        # Each numeric setting has a companion _enabled checkbox.
        # When unchecked the toggle is OFF → store 0 / None (disabled sentinel).
        if request.POST.get("max_batch_size_enabled") == "1":
            try:
                config.max_batch_size = int(request.POST.get("max_batch_size", 50000))
            except (ValueError, TypeError):
                errors["max_batch_size"] = _("Must be a whole number.")
        else:
            config.max_batch_size = 0  # no limit

        if request.POST.get("ppv_tolerance_enabled") == "1":
            tol = request.POST.get("ppv_tolerance_percent", "").strip()
            if tol:
                try:
                    config.ppv_tolerance_percent = Decimal(tol)
                except InvalidOperation:
                    errors["ppv_tolerance_percent"] = _("Must be a valid number.")
                    config.ppv_tolerance_percent = None
            else:
                config.ppv_tolerance_percent = None
        else:
            config.ppv_tolerance_percent = None  # disabled

        # ── review thresholds ──────────────────────────────────────────────
        if request.POST.get("rr_warn_enabled") == "1":
            try:
                config.rejection_rate_warn_threshold = int(request.POST.get("rejection_rate_warn_threshold", 20))
            except (ValueError, TypeError):
                errors["rejection_rate_warn_threshold"] = _("Must be a whole number.")
        else:
            config.rejection_rate_warn_threshold = 0  # no badge

        if request.POST.get("rr_danger_enabled") == "1":
            try:
                config.rejection_rate_danger_threshold = int(request.POST.get("rejection_rate_danger_threshold", 50))
            except (ValueError, TypeError):
                errors["rejection_rate_danger_threshold"] = _("Must be a whole number.")
        else:
            config.rejection_rate_danger_threshold = 0  # no badge

        # ── API throttling ─────────────────────────────────────────────────
        if request.POST.get("api_rate_enabled") == "1":
            try:
                config.api_token_rate_limit = int(request.POST.get("api_token_rate_limit", 1000))
            except (ValueError, TypeError):
                errors["api_token_rate_limit"] = _("Must be a whole number.")
        else:
            config.api_token_rate_limit = 0  # unlimited

        if not errors:
            try:
                config.full_clean()
                config.save()
                messages.success(request, _("System configuration updated."))
                return redirect("control:system_settings")
            except Exception as e:
                if hasattr(e, "message_dict"):
                    errors.update(e.message_dict)
                else:
                    errors["__all__"] = str(e)

    return render(request, "control/system_settings.html", {
        "config": config,
        "errors": errors,
    })


# ===========================================================================
# Sales Review
# ===========================================================================

@perm_required('sales.view_sale')
def sales_list(request):
    """Sales review page — batch list with inline expansion."""
    accounts = Account.objects.order_by("name")
    config   = SystemConfig.get()
    return render(request, "control/sales_list.html", {
        "accounts":      accounts,
        "init_account":  request.GET.get("account",  ""),
        "init_contract": request.GET.get("contract", ""),
        "rr_warn":       config.rejection_rate_warn_threshold,
        "rr_danger":     config.rejection_rate_danger_threshold,
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
            "rejection_rate":  (
                round(b["rejected"] * 100 / (b["accepted"] + b["rejected"]))
                if (b["accepted"] + b["rejected"]) > 0 else -1
            ),
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
    from django.db.models import ExpressionWrapper, FloatField
    from django.db.models.functions import Round
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
        .annotate(pts=Round(ExpressionWrapper(
            F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
            output_field=FloatField(),
        )))
        .order_by("sale_datetime")
    )
    data   = []
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "total_pts": 0}
    for s in qs:
        contract_ppv = s.contract_product.product.ppv
        ppv_mismatch = (contract_ppv is not None and s.ppv != contract_ppv)
        pts = int(s.pts or 0)
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
            "points":           pts,
            "status":           s.status,
            "reviewed_by":      (
                s.reviewed_by.get_full_name() or s.reviewed_by.username
                if s.reviewed_by else None
            ),
            "reviewed_at":      s.reviewed_at.strftime("%d %b %Y, %H:%M") if s.reviewed_at else None,
            "import_received_at": s.sale_import.received_at.strftime("%d %b %Y, %H:%M") if s.sale_import and s.sale_import.received_at else None,
            "sale_created_at":  s.created_at.strftime("%d %b %Y, %H:%M") if s.created_at else None,
        })
        counts[s.status] = counts.get(s.status, 0) + 1
        if s.status == Sale.STATUS_ACCEPTED:
            counts["total_pts"] += pts
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
               "Qty", "PPV", "Contract PU", "PPV OK", "Points",
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
    reason  = request.POST.get("reason", "").strip()
    pks     = [int(p) for p in raw_pks.split(",") if p.strip().isdigit()]
    if status not in (Sale.STATUS_ACCEPTED, Sale.STATUS_REJECTED) or not pks:
        return JsonResponse({"ok": False, "error": "Invalid request"}, status=400)
    update_fields = {
        "status":      status,
        "reviewed_by": request.user,
        "reviewed_at": timezone.now(),
    }
    if status == Sale.STATUS_REJECTED and reason:
        update_fields["rejection_reason"] = reason
    Sale.objects.filter(pk__in=pks).update(**update_fields)
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


# ===========================================================================
# Staff Analytics Dashboard
# ---------------------------------------------------------------------------
# Cross-account points analytics with filters, charts, grouped breakdown
# and CSV export. Permission-gated by control.view_analytics (superuser
# bypass handled by @perm_required).
# ===========================================================================

def _parse_date(s):
    """Return a date from an ISO 'YYYY-MM-DD' string, or None if invalid."""
    from datetime import datetime
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _analytics_filters(request):
    """
    Parse GET params and return (sale_qs, context_dict).

    sale_qs is the Sale queryset narrowed by every active filter EXCEPT the
    status toggle (status is applied downstream where it matters so each
    section can decide — e.g. point KPIs always use accepted-only, while
    the grouped table follows the toggle).

    context_dict carries the raw filter values back to the template so form
    controls can be re-populated.
    """
    from django.db.models import F, ExpressionWrapper, FloatField
    from django.db.models.functions import Round

    date_from     = _parse_date(request.GET.get("date_from"))
    date_to       = _parse_date(request.GET.get("date_to"))
    product_q     = (request.GET.get("product") or "").strip()
    account_id    = (request.GET.get("account") or "").strip()
    contract_id   = (request.GET.get("contract") or "").strip()
    # Active-only toggle: when a specific contract is picked it's a no-op
    # (that contract wins); otherwise narrows to Contract.STATUS_ACTIVE.
    # Default = True (match staff expectation that "contracts" means live ones).
    _ao = (request.GET.get("active_only") or "1").strip().lower()
    active_only   = _ao in ("1", "true", "on", "yes")
    sort_mode     = (request.GET.get("sort") or "points").strip()
    if sort_mode not in ("points", "account"):
        sort_mode = "points"

    qs = Sale.objects.filter(product_ppv__isnull=False)

    if date_from:
        qs = qs.filter(sale_datetime__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_datetime__date__lte=date_to)
    if product_q:
        qs = qs.filter(
            Q(contract_product__product__designation__icontains=product_q)
            | Q(contract_product__product__code__icontains=product_q)
        )
    try:
        if account_id:
            qs = qs.filter(contract_product__contract__account_id=int(account_id))
    except (TypeError, ValueError):
        account_id = ""
    try:
        if contract_id:
            qs = qs.filter(contract_product__contract_id=int(contract_id))
    except (TypeError, ValueError):
        contract_id = ""

    # Active-only narrows the queryset only when NO specific contract was
    # picked (otherwise the explicit pick wins — supports the "look at this
    # inactive contract on purpose" edge case).
    if active_only and not contract_id:
        qs = qs.filter(contract_product__contract__status=Contract.STATUS_ACTIVE)

    qs = qs.annotate(pts=Round(ExpressionWrapper(
        F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
        output_field=FloatField(),
    )))

    ctx = {
        "f_date_from":   date_from.isoformat() if date_from else "",
        "f_date_to":     date_to.isoformat() if date_to else "",
        "f_product":     product_q,
        "f_account":     account_id,
        "f_contract":    contract_id,
        "f_active_only": active_only,
        "f_sort":        sort_mode,
    }
    return qs, ctx


def _month_window(date_from, date_to, now):
    """
    Return (month_dates, month_keys, month_labels, window_start_dt) for the
    monthly chart. Anchors to the filter date range when both bounds are set
    (clamped to 24 months to stay sane); otherwise defaults to trailing 12.
    """
    from datetime import datetime, timezone as dt_tz
    if date_from and date_to and date_to >= date_from:
        start = datetime(date_from.year, date_from.month, 1, tzinfo=dt_tz.utc)
        end   = datetime(date_to.year,   date_to.month,   1, tzinfo=dt_tz.utc)
    else:
        end   = datetime(now.year, now.month, 1, tzinfo=dt_tz.utc)
        y, m  = end.year, end.month - 11
        while m <= 0:
            m += 12
            y -= 1
        start = datetime(y, m, 1, tzinfo=dt_tz.utc)
    months = []
    cur = start
    while cur <= end and len(months) < 24:
        months.append(cur)
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1, tzinfo=dt_tz.utc)
        else:
            cur = datetime(cur.year, cur.month + 1, 1, tzinfo=dt_tz.utc)
    if not months:
        months = [start]
    keys  = [d.strftime("%Y-%m") for d in months]
    lbls  = [d.strftime("%b %Y") for d in months]
    return months, keys, lbls, start


def _previous_period(date_from, date_to):
    """Return (prev_from, prev_to) for the equal-length window just before."""
    from datetime import timedelta
    if not (date_from and date_to) or date_to < date_from:
        return None, None
    span = (date_to - date_from).days + 1
    prev_to   = date_from - timedelta(days=1)
    prev_from = prev_to   - timedelta(days=span - 1)
    return prev_from, prev_to


def _points_sum(request_qs):
    from django.db.models import Sum
    return int(request_qs.filter(status=Sale.STATUS_ACCEPTED).aggregate(t=Sum("pts"))["t"] or 0)


def _compute_analytics(request):
    """
    Core data computation. Enhancements over the first version:
      · month window follows the filter date range when set
      · previous-period comparison KPIs
      · pending-points KPI
      · daily heatmap data
      · top products with 3 metric alternatives (points / qty / revenue)
      · breakdown pagination + inline search
    """
    from datetime import datetime, timezone as dt_tz, timedelta
    from django.db.models import Sum, Count, Avg, Min, F, ExpressionWrapper, FloatField
    from django.db.models.functions import TruncMonth, TruncDay, TruncYear, Round

    qs, filt_ctx = _analytics_filters(request)
    sort_mode     = filt_ctx["f_sort"]

    product_metric = (request.GET.get("metric") or "points").strip()
    if product_metric not in ("points", "qty", "revenue"):
        product_metric = "points"
    tbl_q = (request.GET.get("tbl_q") or "").strip()
    try:
        page = max(1, int(request.GET.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    # Pagination: allowed sizes capped at 100 so one request can't drag back
    # thousands of rows into the browser. Default is 25 — enough for a table
    # that fits on screen without scrolling.
    _ALLOWED_PAGE_SIZES = (10, 25, 50, 100)
    try:
        _ps = int(request.GET.get("page_size") or 25)
    except (TypeError, ValueError):
        _ps = 25
    page_size = _ps if _ps in _ALLOWED_PAGE_SIZES else 25

    # Everything on this page is accepted-sales-only (that's what generates
    # points). scope_qs is kept as an alias so downstream aggregation code
    # stays readable.
    accepted_qs = qs.filter(status=Sale.STATUS_ACCEPTED)
    pending_qs  = qs.filter(status=Sale.STATUS_PENDING)
    scope_qs    = accepted_qs

    now = timezone.now()
    date_from = _parse_date(filt_ctx["f_date_from"])
    date_to   = _parse_date(filt_ctx["f_date_to"])

    # Global time-nav offset shared by every time-aware chart (negative =
    # years back). Only applied when no explicit date filter is set — explicit
    # dates always win.
    try:
        time_offset = int(request.GET.get("time_offset") or 0)
    except (TypeError, ValueError):
        time_offset = 0

    def _shift_year(dt, years):
        """Shift a datetime back/forward by whole years, clamping Feb 29."""
        try:
            return dt.replace(year=dt.year + years)
        except ValueError:
            return dt.replace(year=dt.year + years, day=28)

    month_now = now
    heat_now  = now
    if not date_from and not date_to and time_offset:
        month_now = _shift_year(now, time_offset)
        heat_now  = _shift_year(now, time_offset)

    # ── KPIs ────────────────────────────────────────────────────────────────
    total_points   = int(accepted_qs.aggregate(t=Sum("pts"))["t"] or 0)
    total_products = scope_qs.values("contract_product__product").distinct().count()
    total_accounts = scope_qs.values("contract_product__contract__account").distinct().count()
    pending_points = int(pending_qs.aggregate(t=Sum("pts"))["t"] or 0)

    # Dynamic second KPI: daily average of accepted points over the active
    # window. If date_from/date_to are set, that's the window; otherwise we
    # span the whole data range in scope (earliest sale → today) so the
    # average reflects real activity rather than an arbitrary 30-day slice
    # that may contain no data.
    if date_from and date_to and date_to >= date_from:
        avg_days = (date_to - date_from).days + 1
        total_for_avg = total_points
    else:
        earliest = accepted_qs.aggregate(m=Min("sale_datetime"))["m"]
        if earliest:
            avg_days = max(1, (now.date() - earliest.date()).days + 1)
            total_for_avg = total_points
        else:
            avg_days = 1
            total_for_avg = 0
    daily_avg_points = round(total_for_avg / max(1, avg_days), 1)

    # Previous-period comparison (only when both date bounds set)
    def _pct(curr, prev):
        if not prev:
            return None
        return round(((curr - prev) / prev) * 100.0, 1)

    kpi_prev = {"points": None, "month": None, "products": None, "accounts": None,
                "from": None, "to": None}
    prev_from, prev_to = _previous_period(date_from, date_to)
    if prev_from and prev_to:
        kpi_prev["from"] = prev_from.strftime("%Y-%m-%d")
        kpi_prev["to"]   = prev_to.strftime("%Y-%m-%d")
        # Re-filter the base qs for the previous window; keep account/product/contract filters.
        prev_qs = Sale.objects.filter(product_ppv__isnull=False,
                                      sale_datetime__date__gte=prev_from,
                                      sale_datetime__date__lte=prev_to)
        if filt_ctx["f_product"]:
            prev_qs = prev_qs.filter(
                Q(contract_product__product__designation__icontains=filt_ctx["f_product"])
                | Q(contract_product__product__code__icontains=filt_ctx["f_product"])
            )
        if filt_ctx["f_account"]:
            try:
                prev_qs = prev_qs.filter(contract_product__contract__account_id=int(filt_ctx["f_account"]))
            except ValueError:
                pass
        if filt_ctx["f_contract"]:
            try:
                prev_qs = prev_qs.filter(contract_product__contract_id=int(filt_ctx["f_contract"]))
            except ValueError:
                pass
        prev_qs = prev_qs.annotate(pts=Round(ExpressionWrapper(
            F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
            output_field=FloatField(),
        )))
        prev_acc  = prev_qs.filter(status=Sale.STATUS_ACCEPTED)
        prev_scope = prev_acc
        kpi_prev["points"]   = _pct(total_points,      int(prev_acc.aggregate(t=Sum("pts"))["t"] or 0))
        kpi_prev["products"] = _pct(total_products,    prev_scope.values("contract_product__product").distinct().count())
        kpi_prev["accounts"] = _pct(total_accounts,    prev_scope.values("contract_product__contract__account").distinct().count())

    # ── Timeline chart — adaptive granularity ──────────────────────────────
    # Switch to daily bars when the filtered window is ≤ 60 days; otherwise
    # fall back to monthly (default 12 months when nothing is filtered).
    use_daily = bool(date_from and date_to and (date_to - date_from).days <= 60)

    if use_daily:
        granularity = "day"
        day_count = (date_to - date_from).days + 1
        day_dates = [date_from + timedelta(days=i) for i in range(day_count)]
        timeline_keys  = [d.strftime("%Y-%m-%d") for d in day_dates]
        timeline_lbls  = [d.strftime("%d %b") for d in day_dates]
        window_start   = datetime(date_from.year, date_from.month, date_from.day, tzinfo=dt_tz.utc)

        daily_qs = (
            accepted_qs.filter(sale_datetime__date__gte=date_from, sale_datetime__date__lte=date_to)
            .annotate(bucket=TruncDay("sale_datetime"))
            .values("bucket")
            .annotate(total_pts=Sum("pts"),
                      unique_products=Count("contract_product__product", distinct=True))
        )
        dmap = {r["bucket"].strftime("%Y-%m-%d"): r for r in daily_qs}
        chart_timeline_pts   = [int(dmap.get(k, {}).get("total_pts") or 0) for k in timeline_keys]
        chart_timeline_prods = [dmap.get(k, {}).get("unique_products") or 0 for k in timeline_keys]

        sub_daily = (
            scope_qs.filter(sale_datetime__date__gte=date_from, sale_datetime__date__lte=date_to)
            .annotate(bucket=TruncDay("sale_datetime"))
            .values("bucket")
            .annotate(batches=Count("sale_import__batch_id", distinct=True))
        )
        smap = {r["bucket"].strftime("%Y-%m-%d"): int(r["batches"] or 0) for r in sub_daily}
        chart_submissions = [smap.get(k, 0) for k in timeline_keys]
    else:
        granularity = "month"
        month_dates, timeline_keys, timeline_lbls, window_start = _month_window(date_from, date_to, month_now)
        # Exclusive upper bound = first day of month AFTER the last one in the
        # window. Used both to bound the query and to compute has_next.
        _last_month = month_dates[-1]
        if _last_month.month == 12:
            window_end_excl = datetime(_last_month.year + 1, 1, 1, tzinfo=dt_tz.utc)
        else:
            window_end_excl = datetime(_last_month.year, _last_month.month + 1, 1, tzinfo=dt_tz.utc)
        monthly_qs = (
            accepted_qs.filter(sale_datetime__gte=window_start, sale_datetime__lt=window_end_excl)
            .annotate(bucket=TruncMonth("sale_datetime"))
            .values("bucket")
            .annotate(total_pts=Sum("pts"),
                      unique_products=Count("contract_product__product", distinct=True))
        )
        mmap = {r["bucket"].strftime("%Y-%m"): r for r in monthly_qs}
        chart_timeline_pts   = [int(mmap.get(k, {}).get("total_pts") or 0) for k in timeline_keys]
        chart_timeline_prods = [mmap.get(k, {}).get("unique_products") or 0 for k in timeline_keys]

        sub_qs = (
            scope_qs.filter(sale_datetime__gte=window_start, sale_datetime__lt=window_end_excl)
            .annotate(bucket=TruncMonth("sale_datetime"))
            .values("bucket")
            .annotate(batches=Count("sale_import__batch_id", distinct=True))
        )
        submap = {r["bucket"].strftime("%Y-%m"): int(r["batches"] or 0) for r in sub_qs}
        chart_submissions = [submap.get(k, 0) for k in timeline_keys]

    # Time-nav flags: are there any accepted sales (same scope filters) before
    # the current monthly window / after the current monthly window?
    if granularity == "month":
        month_has_prev = accepted_qs.filter(sale_datetime__lt=window_start).exists()
        month_has_next = (time_offset < 0) and \
            accepted_qs.filter(sale_datetime__gte=window_end_excl).exists()
    else:
        month_has_prev = month_has_next = False

    # Cumulative points — running sum of chart_timeline_pts; same granularity.
    cumulative_pts = []
    _running = 0
    for v in chart_timeline_pts:
        _running += int(v or 0)
        cumulative_pts.append(_running)

    # ── Top products — 3 metric alternatives (points | qty | revenue) ──────
    tp_qs = (
        accepted_qs.values("contract_product__product_id",
                           "contract_product__product__designation")
        .annotate(points=Sum("pts"),
                  qty=Sum("quantity"),
                  revenue=Sum(ExpressionWrapper(
                      F("product_ppv") * F("quantity"), output_field=FloatField()
                  )))
    )
    tp_rows = list(tp_qs)
    def _top(metric_key, n=30):
        out = []
        for r in sorted(tp_rows, key=lambda x: -(float(x[metric_key] or 0)))[:n]:
            v = float(r[metric_key] or 0)
            if v <= 0:
                continue
            out.append({
                "id": r["contract_product__product_id"],
                "name": r["contract_product__product__designation"] or "—",
                "value": round(v, 2) if metric_key == "revenue" else int(v),
            })
        return out
    top_products_sets = {
        "points":  _top("points"),
        "qty":     _top("qty"),
        "revenue": _top("revenue"),
    }

    # ── Points per account ─────────────────────────────────────────────────
    # Enumerate every account "in scope" (has at least one Contract that
    # matches the active filters) and zero-fill the ones without accepted
    # sales — so staff can see which accounts aren't earning instead of them
    # vanishing from the chart. No top-N cap.
    all_accts_qs = Account.objects.filter(contracts__isnull=False)
    if filt_ctx["f_active_only"] and not filt_ctx["f_contract"]:
        all_accts_qs = all_accts_qs.filter(contracts__status=Contract.STATUS_ACTIVE)
    if filt_ctx["f_account"]:
        try:
            all_accts_qs = all_accts_qs.filter(pk=int(filt_ctx["f_account"]))
        except ValueError:
            pass
    if filt_ctx["f_contract"]:
        try:
            all_accts_qs = all_accts_qs.filter(contracts__id=int(filt_ctx["f_contract"]))
        except ValueError:
            pass
    if filt_ctx["f_product"]:
        _pq = filt_ctx["f_product"]
        all_accts_qs = all_accts_qs.filter(
            Q(contracts__contract_product__product__designation__icontains=_pq)
            | Q(contracts__contract_product__product__code__icontains=_pq)
        )
    all_accts_in_scope = list(all_accts_qs.distinct().values("id", "code", "name"))

    pts_rows = (accepted_qs
                .values("contract_product__contract__account_id")
                .annotate(pts=Sum("pts")))
    pts_map = {r["contract_product__contract__account_id"]: int(r["pts"] or 0) for r in pts_rows}

    _acct_pairs = [(a, pts_map.get(a["id"], 0)) for a in all_accts_in_scope]
    _acct_pairs.sort(key=lambda t: (-t[1], (t[0]["name"] or "").lower()))
    chart_acct_labels = [(a["name"] or a["code"] or "—") for a, _ in _acct_pairs]
    chart_acct_data   = [p for _, p in _acct_pairs]
    chart_acct_ids    = [a["id"] for a, _ in _acct_pairs]

    # ── Daily heatmap — respects account/product/contract filters but applies
    # smart date logic:
    #   · no date filter          → last 365 days (long context)
    #   · filter >= 28 days       → the filter range itself
    #   · filter < 28 days        → expand to the enclosing month(s) so a
    #                                single-day or single-week filter still
    #                                shows context around it, not an empty strip.
    import calendar as _cal
    if date_from and date_to:
        span_days = (date_to - date_from).days + 1
        if span_days >= 28:
            heatmap_start = date_from
            heatmap_end   = date_to
        else:
            heatmap_start = date_from.replace(day=1)
            last_day = _cal.monthrange(date_to.year, date_to.month)[1]
            heatmap_end = date_to.replace(day=last_day)
    else:
        heatmap_end  = heat_now.date()
        heatmap_start = heatmap_end - timedelta(days=364)

    hm_qs = (accepted_qs
             .filter(sale_datetime__date__gte=heatmap_start,
                     sale_datetime__date__lte=heatmap_end)
             .annotate(day=TruncDay("sale_datetime"))
             .values("day").annotate(pts=Sum("pts")))

    # Time-nav flags for the heatmap / Points-Awarded group.
    heat_has_prev = accepted_qs.filter(sale_datetime__date__lt=heatmap_start).exists()
    heat_has_next = (time_offset < 0) and \
        accepted_qs.filter(sale_datetime__date__gt=heatmap_end).exists()
    heatmap_data = [[r["day"].strftime("%Y-%m-%d"), int(r["pts"] or 0)] for r in hm_qs]
    heatmap_range = [heatmap_start.strftime("%Y-%m-%d"), heatmap_end.strftime("%Y-%m-%d")]

    # Human-readable scope label used by the heatmap / Points-Awarded cards.
    # When the window matches exactly one calendar month, show just that month;
    # otherwise show the full ISO range.
    if (heatmap_start.day == 1
            and heatmap_end.day == _cal.monthrange(heatmap_end.year, heatmap_end.month)[1]
            and heatmap_start.year == heatmap_end.year
            and heatmap_start.month == heatmap_end.month):
        # Single calendar month → just "YYYY-MM" (the client formats it readably)
        heatmap_scope_label = heatmap_start.strftime("%Y-%m")
    else:
        heatmap_scope_label = ""  # client falls back to "from → to" from heatmap_range

    # Points-Awarded cumulative — shares the heatmap's smart date scope and
    # daily resolution. Reads the same hm_qs result to avoid a second query.
    _by_day = {r["day"].strftime("%Y-%m-%d"): int(r["pts"] or 0) for r in hm_qs}

    # Pre-filter baseline: cumulative points earned by the same account /
    # contract / product scope before the heatmap window begins. Shown as
    # the starting value of the Points-Awarded line, so when the filter
    # lands on an empty range the chart still carries the historical total.
    _baseline_qs = Sale.objects.filter(
        status=Sale.STATUS_ACCEPTED,
        product_ppv__isnull=False,
        sale_datetime__date__lt=heatmap_start,
    ).annotate(_bpts=ExpressionWrapper(
        F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
        output_field=FloatField(),
    ))
    if filt_ctx["f_account"]:
        _baseline_qs = _baseline_qs.filter(contract_product__contract__account_id=int(filt_ctx["f_account"]))
    if filt_ctx["f_contract"]:
        _baseline_qs = _baseline_qs.filter(contract_product__contract_id=int(filt_ctx["f_contract"]))
    if filt_ctx["f_product"]:
        _pq = filt_ctx["f_product"]
        _baseline_qs = _baseline_qs.filter(
            Q(contract_product__product__designation__icontains=_pq)
            | Q(contract_product__product__code__icontains=_pq)
        )
    awarded_baseline = int(round(_baseline_qs.aggregate(t=Sum("_bpts"))["t"] or 0))

    awarded_lbls, awarded_vals = [], []
    _cum, _d = awarded_baseline, heatmap_start
    while _d <= heatmap_end:
        key = _d.strftime("%Y-%m-%d")
        _cum += _by_day.get(key, 0)
        awarded_lbls.append(key)
        awarded_vals.append(_cum)
        _d = _d + timedelta(days=1)

    # ── Breakdown table (two modes: per-sale or grouped) ───────────────────
    # Mode is chosen by the ?group= query param:
    #   ""  / "none"             → per-sale rows (date, contract, product, qty, PU, points)
    #   "account_product"        → one row per (account, product), summed
    bd_group = (request.GET.get("group") or "none").strip().lower()
    if bd_group not in ("none", "account_product"):
        bd_group = "none"

    if bd_group == "account_product":
        # Grouped by (account, contract, product) — the contract is part of
        # the key because the same product under two different contracts can
        # carry a different PU (frozen snapshot) and a different
        # points_per_unit, so collapsing them would mix incomparable rows.
        grouped_rows = list(
            scope_qs.values(
                "contract_product__contract__account_id",
                "contract_product__contract__account__code",
                "contract_product__contract__account__name",
                "contract_product__contract_id",
                "contract_product__contract__title",
                "contract_product__product_id",
                "contract_product__product__code",
                "contract_product__product__designation",
            ).annotate(total_qty=Sum("quantity"),
                       avg_pu=Avg("product_ppv"),
                       total_pts=Sum("pts"))
        )

        def _sort_key(r):
            if sort_mode == "account":
                return ((r["contract_product__contract__account__name"] or "").lower(),
                        (r["contract_product__contract__title"] or "").lower(),
                        (r["contract_product__product__designation"] or "").lower())
            return (-int(r["total_pts"] or 0),
                    (r["contract_product__contract__account__name"] or "").lower())
        grouped_rows.sort(key=_sort_key)

        breakdown_all = [
            {"account_code":   r["contract_product__contract__account__code"] or "",
             "account_name":   r["contract_product__contract__account__name"] or "",
             "contract_title": r["contract_product__contract__title"] or "",
             "product_code":   r["contract_product__product__code"] or "",
             "product_name":   r["contract_product__product__designation"] or "",
             "total_qty":      int(r["total_qty"] or 0),
             "avg_pu":         round(float(r["avg_pu"] or 0), 2),
             "total_pts":      int(r["total_pts"] or 0)}
            for r in grouped_rows
        ]

        if tbl_q:
            tbl_q_low = tbl_q.lower()
            breakdown_all = [r for r in breakdown_all
                             if tbl_q_low in r["account_name"].lower()
                             or tbl_q_low in r["product_name"].lower()
                             or tbl_q_low in r["account_code"].lower()
                             or tbl_q_low in r["product_code"].lower()
                             or tbl_q_low in r["contract_title"].lower()]
    else:
        # Per-sale rows — newest first. Uses Sale.sale_datetime (pharmacy's
        # actual sale time), not SaleImport.received_at.
        per_sale_rows = scope_qs.select_related(
            "contract_product__contract__account",
            "contract_product__product",
        ).order_by("-sale_datetime", "-pk")

        if tbl_q:
            tbl_q_low = tbl_q.lower()
            per_sale_rows = per_sale_rows.filter(
                Q(contract_product__product__designation__icontains=tbl_q_low)
                | Q(contract_product__product__code__icontains=tbl_q_low)
                | Q(contract_product__contract__account__name__icontains=tbl_q_low)
                | Q(contract_product__contract__account__code__icontains=tbl_q_low)
                | Q(contract_product__contract__title__icontains=tbl_q_low)
            )

        breakdown_all = [
            {"sale_datetime": s.sale_datetime.strftime("%Y-%m-%d %H:%M"),
             "account_code":  (s.contract_product.contract.account.code
                               if s.contract_product and s.contract_product.contract else ""),
             "account_name":  (s.contract_product.contract.account.name
                               if s.contract_product and s.contract_product.contract else ""),
             "contract_title": (s.contract_product.contract.title
                                if s.contract_product and s.contract_product.contract else ""),
             "product_code":  (s.contract_product.product.code
                               if s.contract_product and s.contract_product.product else ""),
             "product_name":  (s.contract_product.product.designation
                               if s.contract_product and s.contract_product.product else ""),
             "qty":           int(s.quantity or 0),
             "pu":            round(float(s.product_ppv or 0), 2),
             "pts":           int(s.pts or 0)}
            for s in per_sale_rows
        ]

    total_rows = len(breakdown_all)
    pages = max(1, (total_rows + page_size - 1) // page_size)
    page = min(page, pages)
    offset = (page - 1) * page_size
    breakdown = breakdown_all[offset:offset + page_size]

    # ── Dropdowns ──────────────────────────────────────────────────────────
    all_accounts = list(Account.objects.order_by("name", "code").values("id", "code", "name", "city"))
    # All contracts loaded; the client narrows the dropdown by account_id so
    # the chaining works without an extra round-trip.
    all_contracts = list(
        Contract.objects.select_related("account").order_by("-start_date")
        .values("id", "title", "account_id", "account__code", "status")[:500]
    )

    # Products list for the Product combo. Each entry carries the set of
    # contract_ids and account_ids that cover the product, so the combo can
    # narrow itself when an account or contract filter is active.
    all_products_raw = list(
        Product.objects.filter(status=Product.STATUS_ACTIVE)
        .order_by("designation").values("code", "designation")[:1000]
    )
    cp_rows = list(
        Contract_Product.objects
        .select_related("contract")
        .values("product__designation", "contract_id", "contract__account_id")
    )
    _prod_contracts, _prod_accounts = {}, {}
    for r in cp_rows:
        pname = r["product__designation"]
        if not pname:
            continue
        _prod_contracts.setdefault(pname, set()).add(r["contract_id"])
        _prod_accounts.setdefault(pname, set()).add(r["contract__account_id"])
    all_products = []
    for p in all_products_raw:
        pname = p["designation"]
        all_products.append({
            "code": p["code"],
            "designation": pname,
            "contracts": ",".join(str(x) for x in sorted(_prod_contracts.get(pname, []))),
            "accounts":  ",".join(str(x) for x in sorted(_prod_accounts.get(pname, []))),
        })

    # Years available for the Monthly Overview quick picker (distinct years of
    # accepted sales in the base scope — ignores date filter so switching year
    # is a shortcut to override it).
    year_rows = (Sale.objects.filter(status=Sale.STATUS_ACCEPTED, product_ppv__isnull=False)
                 .annotate(y=TruncYear("sale_datetime"))
                 .values("y").distinct().order_by("-y"))
    years_list = sorted({r["y"].year for r in year_rows if r["y"]}, reverse=True)

    # Lookup maps for filter chips (name resolution client-side via these)
    acct_lookup = {a["id"]: (a["name"] or a["code"]) for a in all_accounts}
    contract_lookup = {c["id"]: c["title"] for c in all_contracts}

    from urllib.parse import urlencode
    export_params = {k.replace("f_", ""): v for k, v in filt_ctx.items()
                     if v and k not in ("f_sort", "f_active_only")}
    # f_active_only defaults to True → only encode when explicitly off.
    if filt_ctx.get("f_active_only") is False:
        export_params["active_only"] = "0"
    if bd_group != "none":
        export_params["group"] = bd_group
    if time_offset:
        export_params["time_offset"] = str(time_offset)
    export_url = f"?{urlencode(export_params)}" if export_params else ""

    return {
        **filt_ctx,
        # KPIs
        "kpi_total_points":    total_points,
        "kpi_daily_avg":       daily_avg_points,
        "kpi_avg_days":        avg_days,
        "kpi_total_products":  total_products,
        "kpi_total_accounts":  total_accounts,
        "kpi_pending_points":  pending_points,
        "kpi_prev":            kpi_prev,
        # Charts
        "chart_timeline_lbls":  timeline_lbls,
        "chart_timeline_keys":  timeline_keys,
        "chart_timeline_pts":   chart_timeline_pts,
        "chart_timeline_prods": chart_timeline_prods,
        "chart_cumulative":     cumulative_pts,
        "chart_granularity":    granularity,
        "chart_submissions":    chart_submissions,
        # Points-Awarded chart (own scope: matches heatmap window)
        "awarded_lbls":         awarded_lbls,
        "awarded_vals":         awarded_vals,
        "chart_top_products":  top_products_sets,
        "chart_acct_labels":   chart_acct_labels,
        "chart_acct_data":     chart_acct_data,
        "chart_acct_ids":      chart_acct_ids,
        "heatmap_data":        heatmap_data,
        "heatmap_range":       heatmap_range,
        "heatmap_scope_label": heatmap_scope_label,
        # Global time-nav state. The window-label strings are rendered
        # client-side via the ISO keys/ranges to keep locale handling there.
        # Both groups' has_prev/next are exposed so the UI can colour each
        # arrow independently (they can differ slightly due to the heatmap's
        # 365-day window vs the month chart's 12-month window).
        "time_offset":         time_offset,
        "month_has_prev":      month_has_prev,
        "month_has_next":      month_has_next,
        "heat_has_prev":       heat_has_prev,
        "heat_has_next":       heat_has_next,
        "month_window_from":   timeline_keys[0] if timeline_keys else "",
        "month_window_to":     timeline_keys[-1] if timeline_keys else "",
        # Breakdown + pagination
        "breakdown":           breakdown,
        "breakdown_total":     total_rows,
        "breakdown_page":      page,
        "breakdown_pages":     pages,
        "breakdown_page_size": page_size,
        "breakdown_q":         tbl_q,
        "breakdown_group":     bd_group,
        "product_metric":      product_metric,
        # Dropdowns
        "all_accounts":        all_accounts,
        "all_contracts":       all_contracts,
        "all_products":        all_products,
        "years_list":          years_list,
        "acct_lookup":         acct_lookup,
        "contract_lookup":     contract_lookup,
        "export_qs":           export_url,
    }


@perm_required("control.view_analytics")
def analytics_dashboard(request):
    """
    Cross-account points analytics dashboard — initial server-render.
    Live updates after load go through analytics_data (JSON endpoint).
    """
    data = _compute_analytics(request)
    # Payloads that are read by the template via <script type="application/json">
    data["breakdown_json"]          = json.dumps(data["breakdown"])
    data["chart_top_products_json"] = json.dumps(data["chart_top_products"])
    data["heatmap_data_json"]       = json.dumps(data["heatmap_data"])
    data["acct_lookup_json"]        = json.dumps(data["acct_lookup"])
    data["contract_lookup_json"]    = json.dumps(data["contract_lookup"])
    data["kpi_prev_json"]           = json.dumps(data["kpi_prev"])
    # Chart arrays inlined inside the main <script>
    for k in ("chart_timeline_lbls", "chart_timeline_keys", "chart_timeline_pts",
              "chart_timeline_prods", "chart_submissions", "chart_cumulative",
              "chart_acct_labels", "chart_acct_data", "chart_acct_ids",
              "heatmap_range", "awarded_lbls", "awarded_vals"):
        data[k] = json.dumps(data[k])
    return render(request, "control/analytics.html", data)


@perm_required("control.view_analytics")
def analytics_data(request):
    """JSON endpoint for live filter updates — same shape as initial context."""
    data = _compute_analytics(request)
    # Drop dropdown data (static client-side); keep everything else as plain
    # Python types so JsonResponse can serialise them.
    data.pop("all_accounts", None)
    data.pop("all_contracts", None)
    return JsonResponse(data)


@perm_required("control.view_analytics")
def analytics_export_csv(request):
    """
    Streaming CSV export of accepted sales matching the current filter —
    one row per sale, chronological. Respects every active filter (date
    range, account, contract, product).
    """
    import csv
    from django.http import StreamingHttpResponse

    qs, filt_ctx = _analytics_filters(request)
    sales = (qs.filter(status=Sale.STATUS_ACCEPTED)
             .select_related("contract_product__product",
                             "contract_product__contract",
                             "contract_product__contract__account")
             .order_by("sale_datetime", "pk"))

    class _Echo:
        def write(self, value): return value
    writer = csv.writer(_Echo())

    bits = []
    if filt_ctx["f_date_from"]:
        bits.append(filt_ctx["f_date_from"])
    if filt_ctx["f_date_to"]:
        bits.append(filt_ctx["f_date_to"])
    date_stamp = "_".join(bits) if bits else "all"
    filename = f'points_{date_stamp}.csv'

    def _rows():
        yield writer.writerow([
            "Sale Date", "Account Code", "Account Name",
            "Contract", "Product Code", "Product",
            "Qty", "PU", "Points",
        ])
        for s in sales.iterator():
            cp  = s.contract_product
            acc = cp.contract.account if cp and cp.contract else None
            yield writer.writerow([
                s.sale_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                acc.code if acc else "",
                acc.name if acc else "",
                cp.contract.title if cp and cp.contract else "",
                cp.product.code if cp and cp.product else "",
                cp.product.designation if cp and cp.product else "",
                s.quantity,
                str(s.product_ppv) if s.product_ppv is not None else "",
                round(float(s.product_ppv or 0) * float(s.quantity or 0) * float(cp.points_per_unit or 0)) if cp else 0,
            ])

    resp = StreamingHttpResponse(_rows(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@perm_required("control.view_analytics")
def analytics_export_xlsx(request):
    """XLSX export of the current analytics grouped breakdown (via openpyxl)."""
    from django.db.models import Sum, Avg
    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    import io

    qs, filt_ctx = _analytics_filters(request)
    sort_mode     = filt_ctx["f_sort"]
    scope_qs      = qs.filter(status=Sale.STATUS_ACCEPTED)

    grouped = list(
        scope_qs.values(
            "contract_product__contract__account__code",
            "contract_product__contract__account__name",
            "contract_product__product__code",
            "contract_product__product__designation",
        ).annotate(total_qty=Sum("quantity"),
                   avg_pu=Avg("product_ppv"),
                   total_pts=Sum("pts"))
    )
    def _sort_key(r):
        if sort_mode == "account":
            return ((r["contract_product__contract__account__name"] or "").lower(),
                    (r["contract_product__product__designation"] or "").lower())
        return (-int(r["total_pts"] or 0),
                (r["contract_product__contract__account__name"] or "").lower())
    grouped.sort(key=_sort_key)

    wb = Workbook()
    ws = wb.active
    ws.title = "Points Breakdown"
    headers = ["Account Code", "Account Name", "Product Code", "Product Designation",
               "Total Qty", "Avg PU", "Total Points"]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1B679B")
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
    for row_idx, r in enumerate(grouped, start=2):
        ws.cell(row=row_idx, column=1, value=r["contract_product__contract__account__code"] or "")
        ws.cell(row=row_idx, column=2, value=r["contract_product__contract__account__name"] or "")
        ws.cell(row=row_idx, column=3, value=r["contract_product__product__code"] or "")
        ws.cell(row=row_idx, column=4, value=r["contract_product__product__designation"] or "")
        ws.cell(row=row_idx, column=5, value=int(r["total_qty"] or 0))
        ws.cell(row=row_idx, column=6, value=round(float(r["avg_pu"] or 0), 2))
        ws.cell(row=row_idx, column=7, value=int(r["total_pts"] or 0))
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 22
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = HttpResponse(buf.read(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = 'attachment; filename="analytics_breakdown.xlsx"'
    return resp


@perm_required("control.view_analytics")
def analytics_product_detail(request, pk):
    """
    JSON payload for the product drill modal: monthly trend over the last
    12 months + top 10 accounts for this product (accepted-only).
    """
    from datetime import datetime, timezone as dt_tz
    from django.db.models import Sum, F, ExpressionWrapper, FloatField
    from django.db.models.functions import Round, TruncMonth

    product = get_object_or_404(Product, pk=pk)

    base = Sale.objects.filter(
        contract_product__product_id=pk,
        status=Sale.STATUS_ACCEPTED,
        product_ppv__isnull=False,
    ).annotate(pts=Round(ExpressionWrapper(
        F("product_ppv") * F("quantity") * F("contract_product__points_per_unit"),
        output_field=FloatField(),
    )))

    now = timezone.now()
    months = []
    for i in range(11, -1, -1):
        m, y = now.month - i, now.year
        while m <= 0:
            m += 12
            y -= 1
        months.append(datetime(y, m, 1, tzinfo=dt_tz.utc))
    month_keys = [d.strftime("%Y-%m") for d in months]
    month_lbls = [d.strftime("%b %Y") for d in months]

    mqs = (base.filter(sale_datetime__gte=months[0])
           .annotate(month=TruncMonth("sale_datetime"))
           .values("month").annotate(pts=Sum("pts"), qty=Sum("quantity")))
    mmap = {r["month"].strftime("%Y-%m"): r for r in mqs}
    month_pts = [int(mmap.get(k, {}).get("pts") or 0) for k in month_keys]
    month_qty = [int(mmap.get(k, {}).get("qty") or 0) for k in month_keys]

    top_acc = list(
        base.values("contract_product__contract__account_id",
                    "contract_product__contract__account__code",
                    "contract_product__contract__account__name")
        .annotate(pts=Sum("pts"), qty=Sum("quantity"))
        .order_by("-pts")[:10]
    )
    top_accounts = [
        {"id":   r["contract_product__contract__account_id"],
         "code": r["contract_product__contract__account__code"] or "",
         "name": r["contract_product__contract__account__name"] or "—",
         "pts":  int(r["pts"] or 0),
         "qty":  int(r["qty"] or 0)}
        for r in top_acc
    ]

    totals = base.aggregate(t=Sum("pts"), q=Sum("quantity"))
    return JsonResponse({
        "id":           product.pk,
        "code":         product.code,
        "designation":  product.designation,
        "ppv":          float(product.ppv) if product.ppv is not None else None,
        "total_points": int(totals["t"] or 0),
        "total_qty":    int(totals["q"] or 0),
        "month_labels": month_lbls,
        "month_pts":    month_pts,
        "month_qty":    month_qty,
        "top_accounts": top_accounts,
    })


@perm_required("control.view_analytics")
def analytics_account_contracts(request, pk):
    """
    Drill payload for a single bar of the "Points per Account" chart.
    Returns the same account's accepted-sale points broken down by contract,
    respecting every active filter EXCEPT the account one (which is
    overridden by `pk` here).
    """
    from django.db.models import Sum

    account = get_object_or_404(Account, pk=pk)

    # Rebuild the filter from the request but force this account. The helper
    # reads account from GET too, so we strip it to avoid double application.
    mutable = request.GET.copy()
    mutable["account"] = str(pk)
    request.GET = mutable
    qs, _ = _analytics_filters(request)

    # List every contract of this account that matches the current filter
    # (status + product), then zero-fill those with no accepted sales so
    # the staff sees which contracts aren't earning yet.
    contracts_qs = Contract.objects.filter(account=account)
    if request.GET.get("active_only", "1") in ("1", "true", "on", "yes") \
            and not request.GET.get("contract"):
        contracts_qs = contracts_qs.filter(status=Contract.STATUS_ACTIVE)
    _pq = (request.GET.get("product") or "").strip()
    if _pq:
        contracts_qs = contracts_qs.filter(
            Q(contract_product__product__designation__icontains=_pq)
            | Q(contract_product__product__code__icontains=_pq)
        )
    contracts_in_scope = list(
        contracts_qs.distinct()
        .order_by("-start_date")
        .values("id", "title", "status")
    )

    pts_rows = (qs.filter(status=Sale.STATUS_ACCEPTED)
                .values("contract_product__contract_id")
                .annotate(pts=Sum("pts")))
    pts_map = {r["contract_product__contract_id"]: int(r["pts"] or 0) for r in pts_rows}

    _pairs = [(c, pts_map.get(c["id"], 0)) for c in contracts_in_scope]
    _pairs.sort(key=lambda t: (-t[1], (t[0]["title"] or "").lower()))
    labels   = [c["title"] or "—" for c, _ in _pairs]
    data     = [p for _, p in _pairs]
    ids      = [c["id"] for c, _ in _pairs]
    statuses = [c["status"] for c, _ in _pairs]
    return JsonResponse({
        "account_id":   account.pk,
        "account_code": account.code,
        "account_name": account.name,
        "labels":       labels,
        "data":         data,
        "ids":          ids,
        "statuses":     statuses,
    })


@perm_required("control.view_analytics")
def analytics_contract_products(request, pk):
    """
    Second-level drill: a single contract's accepted-sale points broken down
    by product. Respects every active filter EXCEPT contract (overridden by
    `pk`). Mirrors analytics_account_contracts in shape.
    """
    from django.db.models import Sum

    contract = get_object_or_404(Contract.objects.select_related("account"), pk=pk)

    mutable = request.GET.copy()
    mutable["contract"] = str(pk)
    # Loosen the active-only lens — if the staff is drilling into a specific
    # (possibly inactive) contract, the explicit pick wins over the toggle.
    mutable["active_only"] = "0"
    request.GET = mutable
    qs, _ = _analytics_filters(request)

    # List every Contract_Product on this contract (zero-fill those without
    # accepted sales so staff see the full catalogue, not just the earners).
    cps = list(
        Contract_Product.objects.filter(contract=contract)
        .select_related("product")
        .order_by("product__designation")
    )

    pts_rows = (qs.filter(status=Sale.STATUS_ACCEPTED)
                .values("contract_product__product_id")
                .annotate(pts=Sum("pts")))
    pts_map = {r["contract_product__product_id"]: int(r["pts"] or 0) for r in pts_rows}

    _pairs = [(cp, pts_map.get(cp.product_id, 0)) for cp in cps]
    _pairs.sort(key=lambda t: (-t[1], (t[0].product.designation or "").lower()))
    labels = [cp.product.designation or "—" for cp, _ in _pairs]
    data   = [p for _, p in _pairs]
    ids    = [cp.product_id for cp, _ in _pairs]
    codes  = [cp.product.code or "" for cp, _ in _pairs]
    return JsonResponse({
        "contract_id":    contract.pk,
        "contract_title": contract.title,
        "account_name":   contract.account.name if contract.account else "",
        "labels":         labels,
        "data":           data,
        "ids":            ids,
        "codes":          codes,
    })
