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

    # Contracts — Part 3
    path("contracts/", coming_soon, name="contracts_list"),
    path("contracts/new/", coming_soon, name="contracts_create"),
    path("contracts/<int:pk>/", coming_soon, name="contracts_detail"),
    path("contracts/<int:pk>/edit/", coming_soon, name="contracts_edit"),
    path("contracts/<int:pk>/delete/", coming_soon, name="contracts_delete"),

    # Products — Part 4
    path("products/", coming_soon, name="products_list"),
    path("products/new/", coming_soon, name="products_create"),
    path("products/<int:pk>/edit/", coming_soon, name="products_edit"),
    path("products/<int:pk>/delete/", coming_soon, name="products_delete"),

    # Users — Part 3
    path("users/", views.users_list, name="users_list"),
    path("users/new/", views.users_create, name="users_create"),
    path("users/<int:pk>/", views.users_detail, name="users_detail"),
    path("users/<int:pk>/edit/", views.users_edit, name="users_edit"),
    path("users/<int:pk>/delete/", views.users_delete, name="users_delete"),

    # API Tokens — Part 6
    path("tokens/", coming_soon, name="tokens_list"),
    path("tokens/new/", coming_soon, name="tokens_create"),
    path("tokens/<int:pk>/delete/", coming_soon, name="tokens_delete"),
]
