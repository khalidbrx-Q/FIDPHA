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

from django.contrib.auth.decorators import user_passes_test


def staff_required(view_func):
    """
    Restrict a view to active staff users only.

    Redirects unauthenticated or non-staff users to the portal login page.
    Wraps Django's user_passes_test decorator with a staff check.

    Args:
        view_func: The view function to protect.

    Returns:
        The decorated view function.
    """
    return user_passes_test(
        lambda user: user.is_active and user.is_staff,
        login_url="/portal/login/",
    )(view_func)
