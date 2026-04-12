from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.shortcuts import redirect, render
from django.contrib import messages
from fidpha import views as fidpha_views
from fidpha.views import CustomPasswordResetView, CustomPasswordResetConfirmView
from fidpha.admin import product_toggle_api
from fidpha.admin import available_products_api, add_contract_product_api

def handler403(request, exception=None):
    return redirect("/admin/")

handler403 = handler403






urlpatterns = [
    path("admin/login/", RedirectView.as_view(url="/portal/login/")),
    path("admin/logout/", fidpha_views.custom_logout),
    path("admin/welcome/", fidpha_views.admin_welcome),
    path("admin/", admin.site.urls),

    path("api/contract/<int:contract_id>/available-products/", available_products_api, name="available_products_api"),
    path("api/contract/<int:contract_id>/add-product/", add_contract_product_api, name="add_contract_product_api"),

    path("api/product/<int:product_id>/toggle/", product_toggle_api, name="product_toggle_api"),

    path("accounts/password_reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("accounts/reset/<uidb64>/<token>/", CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("portal/", include("fidpha.urls")),
    path("auth/", include("allauth.urls")),
    path("", lambda request: redirect("/portal/login/")),
]