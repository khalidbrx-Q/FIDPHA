from django.urls import path

from api.portal_views import (
    PortalAccountView,
    DashboardStatsView,
    DashboardChartsView,
    DashboardRecentSalesView,
    PortalContractsListView,
    PortalActiveContractView,
    ContractChartsView,
    PortalSalesStatsView,
    PortalSalesListView,
    SalesChartsView,
)

urlpatterns = [
    path("account/",                         PortalAccountView.as_view(),         name="portal_account"),
    path("dashboard/stats/",                 DashboardStatsView.as_view(),        name="portal_dashboard_stats"),
    path("dashboard/charts/",                DashboardChartsView.as_view(),       name="portal_dashboard_charts"),
    path("dashboard/recent-sales/",          DashboardRecentSalesView.as_view(),  name="portal_dashboard_recent_sales"),
    path("contracts/",                       PortalContractsListView.as_view(),   name="portal_contracts_list"),
    path("contracts/active/",                PortalActiveContractView.as_view(),  name="portal_active_contract"),
    path("contracts/<int:pk>/charts/",       ContractChartsView.as_view(),        name="portal_contract_charts"),
    path("sales/stats/",                     PortalSalesStatsView.as_view(),      name="portal_sales_stats"),
    path("sales/",                           PortalSalesListView.as_view(),       name="portal_sales_list"),
    path("sales/charts/",                    SalesChartsView.as_view(),           name="portal_sales_charts"),
]
