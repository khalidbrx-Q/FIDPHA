"""
tests/e2e/test_auth.py
----------------------
E2E tests for authentication flows.

Covers:
  - Staff login redirects to control panel
  - Wrong password stays on login page
  - Non-staff cannot access the control panel
  - Logged-out user is redirected to login
  - Logout flow clears session and bounces from protected pages (Tier 1: P21)
  - Anonymous user on portal pages is bounced to login (Tier 1: A2)
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.django_db(transaction=True)
def test_staff_login_redirects_to_control_panel(live_server, page, staff_user, login_as):
    login_as("staff", "StaffPass123!")
    expect(page).to_have_url(f"{live_server.url}/control/")


@pytest.mark.django_db(transaction=True)
def test_wrong_password_stays_on_login_page(live_server, page, staff_user, login_as):
    login_as("staff", "WrongPassword!")
    expect(page).to_have_url(f"{live_server.url}/portal/login/")


@pytest.mark.django_db(transaction=True)
def test_wrong_password_shows_error(live_server, page, staff_user, login_as):
    login_as("staff", "WrongPassword!")
    expect(page.locator("ul.messages")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_unauthenticated_user_redirected_from_control_panel(live_server, page):
    page.goto(f"{live_server.url}/control/")
    expect(page).not_to_have_url(f"{live_server.url}/control/")


# ─── Tier 1 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_logout_clears_session(live_server, page, staff_user, login_as):
    """Tier 1 · P21 — logout via /admin/logout/ clears session; /control/ then bounces."""
    login_as("staff", "StaffPass123!")
    # Confirm we're authenticated and at /control/
    expect(page).to_have_url(f"{live_server.url}/control/")

    # Hit the staff logout URL (per fidpha/views.py:custom_logout → redirects to /portal/login/)
    page.goto(f"{live_server.url}/admin/logout/")
    expect(page).to_have_url(f"{live_server.url}/portal/login/")

    # After logout, /control/ should no longer be accessible
    page.goto(f"{live_server.url}/control/")
    expect(page).not_to_have_url(f"{live_server.url}/control/")


@pytest.mark.django_db(transaction=True)
def test_anonymous_user_redirected_from_portal_dashboard(live_server, page):
    """Tier 1 · A2 — anonymous visitor to /portal/dashboard/ is bounced to login."""
    page.goto(f"{live_server.url}/portal/dashboard/")
    expect(page).not_to_have_url(f"{live_server.url}/portal/dashboard/")


@pytest.mark.django_db(transaction=True)
def test_password_reset_request_lands_on_done_page(live_server, page, staff_user):
    """Tier 1 · A12 — submitting the password reset form leaves the input page.

    The project uses a CustomPasswordResetForm that rejects unknown emails
    (form_invalid → redirects back to itself with session error). So the user
    must actually have a matching email in the DB.
    """
    # The staff_user fixture doesn't set an email — give it one now.
    staff_user.email = "staff@example.com"
    staff_user.save()

    page.goto(f"{live_server.url}/accounts/password_reset/")

    page.fill("[name=email]", "staff@example.com")
    # The form's submit button is the first one (.login-btn); the page also has
    # a language-toggle <button type=submit> in the footer that we must avoid.
    page.locator("form button.login-btn[type=submit]").click()
    page.wait_for_load_state("networkidle")

    # We should have left the form — success redirects to /done/
    expect(page).not_to_have_url(f"{live_server.url}/accounts/password_reset/")


@pytest.mark.django_db(transaction=True)
def test_password_reset_form_with_valid_token_updates_password(live_server, page, staff_user):
    """Tier 1 · A13 — clicking the reset link and submitting a new password works.

    We bypass the email step by generating the (uidb64, token) pair manually
    using Django's default_token_generator, then navigate directly to the
    reset URL, submit a new password, and verify the user can now log in
    with that new password.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    uidb64 = urlsafe_base64_encode(force_bytes(staff_user.pk))
    token = default_token_generator.make_token(staff_user)
    new_password = "BrandNewPass2026!"

    # Visit the reset link. Django's PasswordResetConfirmView stashes the
    # token in the session and redirects to /accounts/reset/<uidb64>/set-password/
    page.goto(f"{live_server.url}/accounts/reset/{uidb64}/{token}/")
    page.wait_for_load_state("networkidle")

    # On the set-password form, fill new_password1 + new_password2 and submit
    page.fill("[name=new_password1]", new_password)
    page.fill("[name=new_password2]", new_password)
    page.locator("button[type=submit], input[type=submit]").first.click()
    page.wait_for_load_state("networkidle")

    # Confirm the password was actually changed in the DB
    staff_user.refresh_from_db()
    assert staff_user.check_password(new_password), (
        "Password reset did not update the stored password"
    )
