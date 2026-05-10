from django.urls import path

from api.staff_views import (
    StaffDashboardStatsView,
    StaffDashboardActivityView,
    StaffAccountsView,
    StaffAccountDetailView,
    StaffContractsView,
    StaffContractDetailView,
    StaffContractChartsView,
    StaffProductsView,
    StaffProductDetailView,
    StaffUsersView,
    StaffUserDetailView,
    StaffRolesView,
    StaffRoleDetailView,
    StaffTokensView,
    StaffTokenDetailView,
    StaffTokenRevokeView,
    StaffTokenReactivateView,
    StaffSaleBatchesView,
    StaffSalesView,
    StaffSaleAcceptView,
    StaffSaleRejectView,
    StaffSalesBulkUpdateView,
    StaffSyncLogView,
    StaffSystemSettingsView,
)

urlpatterns = [
    # Dashboard
    path("dashboard/stats/",                         StaffDashboardStatsView.as_view(),      name="staff_dashboard_stats"),
    path("dashboard/activity/",                      StaffDashboardActivityView.as_view(),   name="staff_dashboard_activity"),

    # Accounts
    path("accounts/",                                StaffAccountsView.as_view(),            name="staff_accounts"),
    path("accounts/<int:pk>/",                       StaffAccountDetailView.as_view(),       name="staff_account_detail"),

    # Contracts
    path("contracts/",                               StaffContractsView.as_view(),           name="staff_contracts"),
    path("contracts/<int:pk>/",                      StaffContractDetailView.as_view(),      name="staff_contract_detail"),
    path("contracts/<int:pk>/charts/",               StaffContractChartsView.as_view(),      name="staff_contract_charts"),

    # Products
    path("products/",                                StaffProductsView.as_view(),            name="staff_products"),
    path("products/<int:pk>/",                       StaffProductDetailView.as_view(),       name="staff_product_detail"),

    # Users
    path("users/",                                   StaffUsersView.as_view(),               name="staff_users"),
    path("users/<int:pk>/",                          StaffUserDetailView.as_view(),          name="staff_user_detail"),

    # Roles
    path("roles/",                                   StaffRolesView.as_view(),               name="staff_roles"),
    path("roles/<int:pk>/",                          StaffRoleDetailView.as_view(),          name="staff_role_detail"),

    # API Tokens
    path("tokens/",                                  StaffTokensView.as_view(),              name="staff_tokens"),
    path("tokens/<int:pk>/",                         StaffTokenDetailView.as_view(),         name="staff_token_detail"),
    path("tokens/<int:pk>/revoke/",                  StaffTokenRevokeView.as_view(),         name="staff_token_revoke"),
    path("tokens/<int:pk>/reactivate/",              StaffTokenReactivateView.as_view(),     name="staff_token_reactivate"),

    # Sales
    path("sales/batches/",                           StaffSaleBatchesView.as_view(),         name="staff_sale_batches"),
    path("sales/",                                   StaffSalesView.as_view(),               name="staff_sales"),
    path("sales/<int:pk>/accept/",                   StaffSaleAcceptView.as_view(),          name="staff_sale_accept"),
    path("sales/<int:pk>/reject/",                   StaffSaleRejectView.as_view(),          name="staff_sale_reject"),
    path("sales/bulk-update/",                       StaffSalesBulkUpdateView.as_view(),     name="staff_sales_bulk_update"),

    # Sync log & system settings (superuser only)
    path("sync-log/",                                StaffSyncLogView.as_view(),             name="staff_sync_log"),
    path("system-settings/",                         StaffSystemSettingsView.as_view(),      name="staff_system_settings"),
]
