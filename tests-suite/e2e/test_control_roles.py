"""
tests/e2e/test_control_roles.py
--------------------------------
E2E tests for the role management flows.

A role in this app is a Django auth.Group plus a 1-1 RoleProfile that stores
the role's icon (defaults to 'badge'). Both must be created together by the
form save.

The permissions picker hides irrelevant framework apps via the _EXCLUDED_APPS
filter in `control/views.py` (`_grouped_permissions`). Apps in that set
(contenttypes, sessions, authtoken, account, socialaccount, sites) must not
appear in the rendered picker — that's R4.

Tier 2 coverage:
  - R3 create Group + RoleProfile via form
  - R4 EXCLUDED_APPS apps are not rendered in the permission picker
"""

import pytest
from playwright.sync_api import expect

from django.contrib.auth.models import Group

from fidpha.models import RoleProfile


@pytest.mark.django_db(transaction=True)
def test_create_role_persists_group_and_role_profile(
    live_server, page, staff_user, login_as
):
    """Tier 2 · R3 — submitting the role form creates both the Group and
    its RoleProfile (the 1-1 model holding the icon)."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/roles/new/")

    page.fill("[name=name]", "Auditor")
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    group = Group.objects.get(name="Auditor")
    # RoleProfile is created in lock-step — its existence is what makes the
    # group appear in the control panel's roles list.
    profile = RoleProfile.objects.get(group=group)
    assert profile.icon == "badge"  # default icon


@pytest.mark.django_db(transaction=True)
def test_permission_picker_hides_excluded_apps(
    live_server, page, staff_user, login_as
):
    """Tier 2 · R4 — apps listed in `_EXCLUDED_APPS` (contenttypes, sessions,
    authtoken, account, socialaccount, sites) never appear in the role form's
    permission picker. Picker groups have `data-app="<app_label>"`."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/roles/new/")

    # Picker must render at least one app group (sanity)
    expect(page.locator(".perm-app-group").first).to_be_attached()

    # And none of the excluded apps should be rendered
    for excluded in ["contenttypes", "sessions", "authtoken", "account",
                     "socialaccount", "sites"]:
        expect(page.locator(f".perm-app-group[data-app='{excluded}']")).to_have_count(
            0, timeout=1000
        )

    # Sanity check: a relevant app SHOULD be present
    expect(page.locator(".perm-app-group[data-app='fidpha']")).to_have_count(1)
