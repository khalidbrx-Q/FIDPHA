"""
tests/e2e/test_control_dashboard.py
------------------------------------
E2E tests for the staff control panel dashboard at /control/.

The dashboard renders 5 KPI stat cards (Accounts / Contracts / Products /
Users / API Tokens) and a "Recent Activity" widget driven by Django's
LogEntry model (the same audit log written by `_log()` in control/views.py).

Tier 2 coverage:
  - D2 KPI cards show real counts from the DB
  - D3 activity log lists CRUD events
"""

import pytest
from playwright.sync_api import expect

from django.contrib.admin.models import ADDITION, LogEntry

from fidpha.models import Account
from fidpha.services import STATUS_ACTIVE


@pytest.mark.django_db(transaction=True)
def test_dashboard_kpi_cards_show_real_counts(
    live_server, page, staff_user, login_as
):
    """Tier 2 · D2 — counts on the KPI cards reflect the actual DB state.

    Creates one active Account, then asserts the "Accounts" stat-card shows
    a value >= 1 (the existing staff superuser plus the new account guarantee
    a non-zero baseline across all 5 cards).
    """
    Account.objects.create(
        code="PH-DASH", name="Dashboard Pharmacy", city="Casablanca",
        location="1 Rue", phone="0600000000", email="dash@p.ma",
        pharmacy_portal=True, status=STATUS_ACTIVE,
    )

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/")

    # The Accounts card's stat-value should be at least 1
    accounts_card = page.locator(".stat-card", has_text="Accounts").first
    expect(accounts_card.locator(".stat-value")).to_have_text("1")

    # Users card includes the superuser
    users_card = page.locator(".stat-card", has_text="Users").first
    val = users_card.locator(".stat-value").text_content()
    assert val and int(val) >= 1


@pytest.mark.django_db(transaction=True)
def test_dashboard_recent_activity_lists_crud_events(
    live_server, page, staff_user, login_as
):
    """Tier 2 · D3 — the Recent Activity widget renders entries from LogEntry.

    Writes a LogEntry directly (same path control views use via `_log()`),
    then verifies the entry appears in the dashboard's activity card with the
    actor's name and the object_repr.
    """
    acct = Account.objects.create(
        code="PH-ACT", name="Activity Pharmacy", city="Casablanca",
        location="1 Rue", phone="0600000000", email="act@p.ma",
        pharmacy_portal=True, status=STATUS_ACTIVE,
    )
    LogEntry.objects.log_actions(
        user_id=staff_user.pk,
        queryset=[acct],
        action_flag=ADDITION,
        change_message="Created via Tier 2 test",
        single_object=True,
    )

    login_as("staff", "StaffPass123!")
    page.goto(f"{live_server.url}/control/")

    # The activity card has the title "Recent Activity"
    activity_card = page.locator(".card", has_text="Recent Activity").first
    expect(activity_card).to_be_visible()

    # The actor's username and the object_repr should both show up inside it
    expect(activity_card.get_by_text(staff_user.username).first).to_be_visible()
    expect(activity_card.get_by_text(str(acct)).first).to_be_visible()
