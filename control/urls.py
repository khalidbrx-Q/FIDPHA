"""
control/urls.py
---------------
URL routes for the custom admin control panel.

All routes are prefixed with /control/ in the main urls.py.
New routes will be added here as each part of the control panel is built.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

"""
control/urls.py
---------------
URL routes for the custom admin control panel.

All routes are prefixed with /control/ in the main urls.py.
Placeholder views (coming_soon) are used for sections not yet built —
they will be replaced part by part as the control panel grows.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from django.urls import path
from django.shortcuts import render
from .decorators import staff_required
from . import views

app_name = "control"


def coming_soon(request):
    """Temporary placeholder for sections not yet built."""
    return render(request, "control/coming_soon.html")


coming_soon = staff_required(coming_soon)

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Roles — Part 2
    path("roles/", views.roles_list, name="roles_list"),
    path("roles/new/", views.roles_create, name="roles_create"),
    path("roles/<int:pk>/", views.roles_detail, name="roles_detail"),
    path("roles/<int:pk>/edit/", views.roles_edit, name="roles_edit"),
    path("roles/<int:pk>/delete/", views.roles_delete, name="roles_delete"),

    # Accounts
    path("accounts/", views.accounts_list, name="accounts_list"),
    path("accounts/new/", views.accounts_create, name="accounts_create"),
    path("accounts/<int:pk>/", views.accounts_detail, name="accounts_detail"),
    path("accounts/<int:pk>/edit/", views.accounts_edit, name="accounts_edit"),
    path("accounts/<int:pk>/delete/", views.accounts_delete, name="accounts_delete"),

    # Contracts
    path("contracts/", views.contracts_list, name="contracts_list"),
    path("contracts/new/", views.contracts_create, name="contracts_create"),
    path("contracts/<int:pk>/", views.contracts_detail, name="contracts_detail"),
    path("contracts/<int:pk>/edit/", views.contracts_edit, name="contracts_edit"),
    path("contracts/<int:pk>/delete/", views.contracts_delete, name="contracts_delete"),

    # Products
    path("products/", views.products_list, name="products_list"),
    path("products/new/", views.products_create, name="products_create"),
    path("products/<int:pk>/", views.products_detail, name="products_detail"),
    path("products/<int:pk>/edit/", views.products_edit, name="products_edit"),
    path("products/<int:pk>/delete/", views.products_delete, name="products_delete"),

    # Users — Part 3
    path("users/", views.users_list, name="users_list"),
    path("users/new/", views.users_create, name="users_create"),
    path("users/<int:pk>/", views.users_detail, name="users_detail"),
    path("users/<int:pk>/edit/", views.users_edit, name="users_edit"),
    path("users/<int:pk>/delete/", views.users_delete, name="users_delete"),

    # API Tokens
    path("tokens/", views.tokens_list, name="tokens_list"),
    path("tokens/new/", views.tokens_create, name="tokens_create"),
    path("tokens/<int:pk>/", views.tokens_detail, name="tokens_detail"),
    path("tokens/<int:pk>/revoke/", views.tokens_revoke, name="tokens_revoke"),
    path("tokens/<int:pk>/reactivate/", views.tokens_reactivate, name="tokens_reactivate"),
    path("tokens/<int:pk>/delete/", views.tokens_delete, name="tokens_delete"),

    # Sales Review
    path("sales/",                   views.sales_list,         name="sales_list"),
    path("sales/<int:pk>/accept/",   views.sale_accept,        name="sale_accept"),
    path("sales/<int:pk>/reject/",   views.sale_reject,        name="sale_reject"),
    path("sales/bulk-accept/",       views.sales_bulk_accept,  name="sales_bulk_accept"),
    path("sales/bulk-update/",       views.sales_bulk_update,  name="sales_bulk_update"),
    path("sales/api/contracts/",     views.sales_api_contracts,  name="sales_api_contracts"),
    path("sales/api/batches/",       views.sales_api_batches,    name="sales_api_batches"),
    path("sales/api/batches-v2/",    views.sales_api_batches_v2, name="sales_api_batches_v2"),
    path("sales/api/sales/",         views.sales_api_sales,      name="sales_api_sales"),
    path("sales/export/",            views.sales_export_csv,      name="sales_export_csv"),
    path("sales/export-list/",       views.sales_export_list_csv, name="sales_export_list_csv"),

    # Configuration — Social Accounts
    path("settings/social-accounts/", views.social_accounts_list, name="social_accounts_list"),
    path("settings/social-accounts/<int:pk>/unlink/", views.social_account_unlink, name="social_account_unlink"),

    # Configuration — Social Applications
    path("settings/social-apps/", views.social_apps_list, name="social_apps_list"),
    path("settings/social-apps/new/", views.social_apps_create, name="social_apps_create"),
    path("settings/social-apps/<int:pk>/", views.social_apps_detail, name="social_apps_detail"),
    path("settings/social-apps/<int:pk>/edit/", views.social_apps_edit, name="social_apps_edit"),
    path("settings/social-apps/<int:pk>/delete/", views.social_apps_delete, name="social_apps_delete"),

    # Configuration — Site
    path("settings/site/", views.site_edit, name="site_edit"),

    # Configuration — System
    path("settings/system/", views.system_settings, name="system_settings"),

    # Sync Import Log (superuser debug)
    path("sync-log/", views.sync_log, name="sync_log"),
]
