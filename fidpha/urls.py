from django.urls import path
from . import views

app_name = "fidpha"

urlpatterns = [
    path("login/", views.custom_login, name="login"),
    path("dashboard/", views.portal_dashboard, name="dashboard"),
    path("pharmacy/", views.portal_pharmacy, name="pharmacy"),
    path("contracts/", views.portal_contracts, name="contracts"),
    path("setup-profile/", views.setup_profile, name="setup_profile"),
    path("verify-pending/", views.verify_pending, name="verify_pending"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("profile/", views.portal_profile, name="profile"),
    path("logout/", views.custom_logout, name="logout"),
    path("profile/password/", views.portal_profile_password, name="profile_password"),
    path("sales/", views.portal_sales, name="sales"),
]