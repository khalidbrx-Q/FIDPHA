"""
control/decorators.py
---------------------
Access control decorators for the custom admin control panel.

Every view in the control panel must be decorated with @staff_required
to ensure only active staff users can access it. Non-staff users are
redirected to the portal login page.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render


def staff_required(view_func):
    """Restrict a view to active staff users only."""
    return user_passes_test(
        lambda user: user.is_active and user.is_staff,
        login_url="/portal/login/",
    )(view_func)


def perm_required(perm):
    """
    Restrict a view to staff users who also hold a specific Django permission.
    Superusers bypass the permission check. Non-staff are redirected to login.
    Unauthorised staff see a 403 page.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not (request.user.is_active and request.user.is_staff):
                return redirect("/portal/login/")
            if not request.user.is_superuser and not request.user.has_perm(perm):
                return render(request, "control/403.html", status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def superuser_required(view_func):
    """Restrict a view to superusers only."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_active and request.user.is_staff):
            return redirect("/portal/login/")
        if not request.user.is_superuser:
            return render(request, "control/403.html", status=403)
        return view_func(request, *args, **kwargs)
    return wrapper
