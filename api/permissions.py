from rest_framework.permissions import BasePermission

from fidpha.models import Account


class HasAPIToken(BasePermission):
    def has_permission(self, request, view):
        return request.auth is not None


class PortalSessionPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user is None:
            return False
        if not request.user.is_authenticated or not request.user.is_active:
            return False
        if request.user.is_staff:
            return False
        try:
            account = request.user.profile.account
            return (
                account.pharmacy_portal is True
                and account.status == Account.STATUS_ACTIVE
            )
        except Exception:
            return False


class StaffSessionPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user is None:
            return False
        return (
            request.user.is_authenticated
            and request.user.is_active
            and request.user.is_staff
        )