"""
control/forms.py
----------------
Forms for the custom admin control panel.

Each form maps directly to a model or a subset of model fields.
Business rule validation stays in the model's clean() method —
forms call full_clean() before saving so those rules are enforced
without duplication here.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from django import forms
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.password_validation import validate_password

from fidpha.models import Account, UserProfile


class RoleForm(forms.ModelForm):
    """
    Form for creating and editing Roles (Django Groups).

    Permissions are rendered as grouped checkboxes in the template
    rather than the default dual-listbox widget, grouped by app label
    for readability.
    """

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "content_type__model", "codename"
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({
            "class": "form-input",
            "placeholder": "e.g. Accounts Manager",
            "autocomplete": "off",
        })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserForm(forms.Form):
    """
    Unified create / edit form for all user types.

    Handles three user types whose fields differ:
      - superuser  : basic info + password only
      - staff      : basic info + password + role (Group)
      - portal     : basic info + password + account + email_verified

    On edit mode (instance is provided), password fields are optional —
    leaving them blank keeps the existing password unchanged.

    save() applies all persistence: User, groups, and UserProfile.
    """

    USER_TYPE_CHOICES = [
        ("superuser", "Superuser"),
        ("staff",     "Staff"),
        ("portal",    "Portal User"),
    ]

    # ---- Basic info ----
    username   = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name  = forms.CharField(max_length=150, required=False)
    email      = forms.EmailField(required=False)
    is_active  = forms.BooleanField(required=False, initial=True)

    # ---- Type selector ----
    user_type  = forms.ChoiceField(choices=USER_TYPE_CHOICES, initial="portal")

    # ---- Password ----
    password1 = forms.CharField(required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(required=False, widget=forms.PasswordInput)

    # ---- Staff-specific ----
    role = forms.ModelChoiceField(
        queryset=Group.objects.order_by("name"),
        required=False,
        empty_label="— No role assigned —",
    )

    # ---- Portal-specific ----
    account = forms.ModelChoiceField(
        queryset=Account.objects.order_by("name"),
        required=False,
        empty_label="— Select account —",
    )
    # email_verified is display-only in the UI — not editable through this form.
    # It is set by the portal's email verification flow, not the admin.

    def __init__(self, *args, instance: User | None = None, **kwargs):
        self.instance = instance
        self.is_edit  = instance is not None
        super().__init__(*args, **kwargs)

        # Apply consistent CSS to all text-like inputs
        text_fields = ["username", "first_name", "last_name", "email", "password1", "password2"]
        for name in text_fields:
            self.fields[name].widget.attrs["class"] = "form-input"

        self.fields["username"].widget.attrs["autocomplete"]  = "off"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self.fields["role"].widget.attrs["class"]    = "form-input"
        self.fields["account"].widget.attrs["class"] = "form-input"

        # Pre-fill fields when editing an existing user
        if self.is_edit and not args and "data" not in kwargs:
            u = instance
            self.fields["username"].initial   = u.username
            self.fields["first_name"].initial = u.first_name
            self.fields["last_name"].initial  = u.last_name
            self.fields["email"].initial      = u.email
            self.fields["is_active"].initial  = u.is_active

            if u.is_superuser:
                self.fields["user_type"].initial = "superuser"
            elif u.is_staff:
                self.fields["user_type"].initial = "staff"
                first_group = u.groups.first()
                # Use pk so template comparison works reliably
                self.fields["role"].initial = first_group.pk if first_group else None
            else:
                self.fields["user_type"].initial = "portal"
                try:
                    profile = u.profile
                    # Use pk so the select option comparison works reliably
                    self.fields["account"].initial = profile.account_id
                except UserProfile.DoesNotExist:
                    pass

    # ---- Validation ----

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username)
        if self.is_edit:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def clean(self):
        cleaned = super().clean()
        user_type = cleaned.get("user_type")
        p1 = (cleaned.get("password1") or "").strip()
        p2 = (cleaned.get("password2") or "").strip()

        # Password: required on create, optional on edit
        if not self.is_edit and not p1:
            self.add_error("password1", "Password is required when creating a user.")
        elif p1 or p2:
            if p1 != p2:
                self.add_error("password2", "Passwords do not match.")
            elif p1:
                try:
                    validate_password(p1)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)

        # Portal user must have an account
        if user_type == "portal" and not cleaned.get("account"):
            self.add_error("account", "Please select an account for this portal user.")

        return cleaned

    # ---- Persistence ----

    def save(self) -> User:
        """
        Persist the user, their type flags, groups, and UserProfile.

        Returns the saved User instance.
        """
        data      = self.cleaned_data
        user_type = data["user_type"]

        user = self.instance if self.is_edit else User()
        user.username   = data["username"]
        user.first_name = data.get("first_name", "")
        user.last_name  = data.get("last_name", "")
        user.email      = data.get("email") or ""
        user.is_active  = data.get("is_active", True)
        user.is_superuser = (user_type == "superuser")
        user.is_staff     = (user_type in ("superuser", "staff"))

        p1 = (data.get("password1") or "").strip()
        if p1:
            user.set_password(p1)
        elif not self.is_edit:
            user.set_unusable_password()

        user.save()

        # Assign role (group) for staff users; clear for all others
        if user_type == "staff" and data.get("role"):
            user.groups.set([data["role"]])
        else:
            user.groups.clear()

        # Individual permissions are not used — always clear
        user.user_permissions.clear()

        # Create / update UserProfile for portal users; remove for others
        if user_type == "portal":
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.account = data["account"]
            # email_verified is managed by the portal flow — never overwrite it here
            profile.save()
        else:
            UserProfile.objects.filter(user=user).delete()

        return user
