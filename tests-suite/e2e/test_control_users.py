"""
tests/e2e/test_control_users.py
--------------------------------
E2E tests for the user management flows in the control panel.

The control/users/ form is a custom UI:
  - user_type is a radio (superuser/staff/portal)
  - role and account are hidden inputs driven by a custom-select widget
    (`csSelect(cs_id, value, label)`). Tests set the hidden value directly
    via JS because emulating the dropdown click sequence is brittle and
    the focus here is the persisted state, not the dropdown UI.

Tier 2 coverage:
  - U6  staff user with role can log in after being created via the UI
  - U7  portal user linked to an account can log in after creation
  - U13 editing a user's role updates user.groups in the DB
  - U14 deactivating a user blocks subsequent login attempts
"""

import pytest
from playwright.sync_api import expect

from django.contrib.auth.models import Group, User

from fidpha.models import Account, UserProfile
from fidpha.services import STATUS_ACTIVE


def _set_hidden(page, name, value):
    """Set a hidden form input's value via JS — used for the custom-select widgets."""
    page.locator(f"[name='{name}']").evaluate("(el, v) => el.value = v", str(value))


def _select_user_type(page, user_type):
    """The user_type radios live inside styled .type-card labels and are positioned
    off-screen. Toggle checked + fire the change event the form's JS listens to."""
    page.locator(f"input[name=user_type][value={user_type}]").evaluate(
        "el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles:true})); }"
    )


@pytest.fixture
def role_with_perms(db):
    """A Group named 'Reviewer' — gives us a known target role for U6/U13."""
    return Group.objects.create(name="Reviewer")


@pytest.fixture
def other_role(db):
    """A second Group for U13 — switching from one role to another."""
    return Group.objects.create(name="Manager")


@pytest.fixture
def account_for_portal(db):
    return Account.objects.create(
        code="PH-U7", name="U7 Pharmacy", city="Casablanca", location="1 Rue",
        phone="0600000000", email="u7@pharmacy.ma",
        pharmacy_portal=True, status=STATUS_ACTIVE,
    )


@pytest.mark.django_db(transaction=True)
def test_create_staff_user_with_role_can_login(
    live_server, page, staff_user, role_with_perms, login_as
):
    """Tier 2 · U6 — superuser creates a staff user + role via the form;
    new user logs in and lands on /control/."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/users/new/")

    page.fill("[name=username]", "newstaff")
    page.fill("[name=password1]", "NewStaffPass123!")
    page.fill("[name=password2]", "NewStaffPass123!")
    _select_user_type(page, "staff")
    _set_hidden(page, "role", role_with_perms.pk)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    new_user = User.objects.get(username="newstaff")
    assert new_user.is_staff is True
    assert new_user.is_superuser is False
    assert list(new_user.groups.values_list("name", flat=True)) == ["Reviewer"]

    # Logout + login as the newly created staff user
    page.goto(f"{live_server.url}/admin/logout/")
    page.wait_for_load_state("networkidle")
    login_as("newstaff", "NewStaffPass123!")
    expect(page).to_have_url(f"{live_server.url}/control/")


@pytest.mark.django_db(transaction=True)
def test_create_portal_user_linked_to_account_can_login(
    live_server, page, staff_user, account_for_portal, login_as
):
    """Tier 2 · U7 — superuser creates a portal user with an account link.
    The new user logs in and is sent to /portal/dashboard/."""
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/users/new/")

    page.fill("[name=username]", "newportal")
    page.fill("[name=password1]", "NewPortalPass123!")
    page.fill("[name=password2]", "NewPortalPass123!")
    _select_user_type(page, "portal")
    _set_hidden(page, "account", account_for_portal.pk)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    new_user = User.objects.get(username="newportal")
    assert new_user.is_staff is False
    profile = UserProfile.objects.get(user=new_user)
    assert profile.account_id == account_for_portal.pk

    # Logout + login as the newly created portal user
    page.goto(f"{live_server.url}/admin/logout/")
    page.wait_for_load_state("networkidle")
    login_as("newportal", "NewPortalPass123!")
    expect(page).to_have_url(f"{live_server.url}/portal/dashboard/")


@pytest.mark.django_db(transaction=True)
def test_edit_user_role_change_persists(
    live_server, page, staff_user, role_with_perms, other_role, login_as
):
    """Tier 2 · U13 — switching a staff user's role through the form replaces
    user.groups with the new role (UserForm.save() always calls groups.set/clear).
    """
    target = User.objects.create_user(
        username="rotated", password="RotatedPass123!", is_staff=True,
    )
    target.groups.set([role_with_perms])  # starts as Reviewer

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/users/{target.pk}/edit/")
    _set_hidden(page, "role", other_role.pk)
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    target.refresh_from_db()
    assert list(target.groups.values_list("name", flat=True)) == ["Manager"]


@pytest.mark.django_db(transaction=True)
def test_deactivated_user_cannot_login(
    live_server, page, staff_user, login_as
):
    """Tier 2 · U14 — flipping is_active off through the edit form blocks login.

    Django's auth backend rejects inactive users before checking the password,
    so the login form must stay on /portal/login/ with no session created.
    """
    target = User.objects.create_user(
        username="deactivated", password="DeactivatedPass123!", is_staff=True,
    )

    # Superuser edits the target user and unchecks is_active
    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/users/{target.pk}/edit/")
    # is_active is a styled toggle switch — the underlying checkbox is visually
    # hidden, so set it via JS and fire change for any listeners.
    page.locator("[name=is_active]").evaluate(
        "el => { el.checked = false; el.dispatchEvent(new Event('change', {bubbles:true})); }"
    )
    page.locator("#submitBtn").click()
    page.wait_for_load_state("networkidle")

    target.refresh_from_db()
    assert target.is_active is False

    # Logout + attempt login as the deactivated user
    page.goto(f"{live_server.url}/admin/logout/")
    page.wait_for_load_state("networkidle")
    login_as("deactivated", "DeactivatedPass123!")
    # Login form must reject the attempt — URL stays on /portal/login/
    expect(page).to_have_url(f"{live_server.url}/portal/login/")
