"""
tests-suite/unit/test_control.py
---------------------------------
Unit tests for the control panel's server-side logic — pages whose behaviour
isn't worth a full Playwright run.

  DashboardActivityFilterTests  — the dashboard's "Recent Activity" widget
                                  is filtered by the viewer's view-perms so
                                  staff don't see audit entries on resources
                                  they can't view.
"""

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase

from fidpha.models import Account
from fidpha.services import STATUS_ACTIVE
from api.models import APIToken


class DashboardActivityFilterTests(TestCase):
    """The /control/ dashboard's recent_activity context must respect the
    viewer's permissions:

      - Superusers see every LogEntry.
      - Staff users only see entries on content types they have `view_*`
        permission for.
      - A staff user with no view perms at all sees an empty list.
    """

    def setUp(self):
        # ── Users ─────────────────────────────────────────────────────────
        self.superuser = User.objects.create_user(
            username="superuser", password="pw", is_staff=True, is_superuser=True,
        )
        self.limited_staff = User.objects.create_user(
            username="limited", password="pw", is_staff=True, is_superuser=False,
        )
        # Grant ONLY api.view_apitoken — not fidpha.view_account.
        self.limited_staff.user_permissions.add(
            Permission.objects.get(codename="view_apitoken")
        )

        self.no_perms_staff = User.objects.create_user(
            username="noperms", password="pw", is_staff=True, is_superuser=False,
        )

        # ── Audit log: one Account entry + one APIToken entry ─────────────
        self.account = Account.objects.create(
            code="PH-LOG", name="Log Pharmacy", city="C", location="L",
            phone="0600000000", email="log@p.ma",
            pharmacy_portal=True, status=STATUS_ACTIVE,
        )
        token_obj = APIToken(name="Log Token")
        token_obj.save()

        LogEntry.objects.log_actions(
            user_id=self.superuser.pk, queryset=[self.account],
            action_flag=ADDITION, change_message="created via setUp",
            single_object=True,
        )
        LogEntry.objects.log_actions(
            user_id=self.superuser.pk, queryset=[token_obj],
            action_flag=ADDITION, change_message="created via setUp",
            single_object=True,
        )

    def _activity_content_type_models(self, response):
        """Pluck the `model` of each LogEntry's content_type from the
        rendered context — order-independent."""
        return sorted(
            entry.content_type.model
            for entry in response.context["recent_activity"]
        )

    def test_superuser_sees_all_audit_entries(self):
        """Superusers retain the original "see everything" behaviour."""
        client = Client()
        client.force_login(self.superuser)
        response = client.get("/control/")
        self.assertEqual(response.status_code, 200)
        # Both entries present
        self.assertEqual(
            self._activity_content_type_models(response),
            ["account", "apitoken"],
        )

    def test_limited_staff_sees_only_permitted_content_types(self):
        """Staff user with only `api.view_apitoken` sees the token entry,
        NOT the account entry (no `fidpha.view_account` permission)."""
        client = Client()
        client.force_login(self.limited_staff)
        response = client.get("/control/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._activity_content_type_models(response),
            ["apitoken"],
        )

    def test_staff_with_no_view_perms_sees_empty_activity(self):
        """Staff user with zero view permissions gets an empty queryset
        (rather than a leak of every audit row)."""
        client = Client()
        client.force_login(self.no_perms_staff)
        response = client.get("/control/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["recent_activity"]), [])
