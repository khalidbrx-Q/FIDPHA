from rest_framework.permissions import BasePermission

class HasAPIToken(BasePermission):
    def has_permission(self, request, view):
        return request.auth is not None