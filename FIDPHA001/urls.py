from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.shortcuts import redirect, render
from django.contrib import messages
from fidpha import views as fidpha_views
from fidpha.views import CustomPasswordResetView, CustomPasswordResetConfirmView
# These admin AJAX helpers live in admin_api.py, not admin.py —
# admin.py is reserved for admin panel registration only.
from fidpha.admin_api import (
    product_toggle_api,
    available_products_api,
    add_contract_product_api,
)

def handler403(request, exception=None):
    return redirect("/control/")

handler403 = handler403


def spa_view(request, subpath=""):
    return render(request, "react/index.html")


def staff_spa_view(request, subpath=""):
    return render(request, "react/staff_index.html")






urlpatterns = [
    path("admin/login/", RedirectView.as_view(url="/portal/login/")),
    path("admin/logout/", fidpha_views.custom_logout),
    path("admin/welcome/", fidpha_views.admin_welcome),
    # path("admin/", admin.site.urls),  # disabled — replaced by /control/

    path("api/contract/<int:contract_id>/available-products/", available_products_api, name="available_products_api"),
    path("api/contract/<int:contract_id>/add-product/", add_contract_product_api, name="add_contract_product_api"),

    path("api/product/<int:product_id>/toggle/", product_toggle_api, name="product_toggle_api"),

    path("accounts/password_reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("accounts/reset/<uidb64>/<token>/", CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("portal/", include("fidpha.urls")),
    path("auth/", include("allauth.urls")),
    path("", lambda request: redirect("/portal/login/")),

    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", include("api.urls")),
    path("api/portal/", include("api.portal_urls")),
    path("api/staff/", include("api.staff_urls")),

    # SPA entry points — served once React bundles are built
    path("app/", spa_view),
    path("app/<path:subpath>", spa_view),
    path("control-app/", staff_spa_view),
    path("control-app/<path:subpath>", staff_spa_view),

    # Custom admin control panel — staff only, Django admin kept as fallback
    path("control/", include("control.urls")),
]