from django.urls import path
from .views import ActiveContractView, SalesSubmitView

urlpatterns = [
    path("contract/active/", ActiveContractView.as_view(), name="active_contract"),
    path("sales/",           SalesSubmitView.as_view(),   name="sales_submit"),
]
