from django.urls import path
from .views import ActiveContractView

urlpatterns = [
    path("contract/active/", ActiveContractView.as_view(), name="active_contract"),
]