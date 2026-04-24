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
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.contrib.sites.models import Site
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet

from allauth.socialaccount.models import SocialApp
from allauth.socialaccount import providers as allauth_providers

from fidpha.models import Account, Contract, Contract_Product, Product, UserProfile
from api.models import APIToken


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

class AccountForm(forms.ModelForm):
    """
    Form for creating and editing pharmacy accounts.

    Uses ModelForm so Django's _post_clean() automatically calls the model's
    clean() method — which enforces the "cannot deactivate with active
    contracts" business rule — and surfaces it as a non-field error.
    """

    class Meta:
        model  = Account
        fields = ['code', 'name', 'city', 'location', 'phone',
                  'email', 'pharmacy_portal', 'status']
        widgets = {
            'location': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname in ['code', 'name', 'city', 'phone', 'email']:
            self.fields[fname].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['location'].widget.attrs.update({'class': 'form-input'})
        self.fields['status'].widget.attrs.update({'class': 'form-input'})

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        qs = Account.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('An account with this code already exists.')
        return code


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

class AccountSelect(forms.Select):
    """
    Select widget that adds data-name, data-code, data-city HTML attributes to
    each <option> so the JS custom dropdown can render rich two-line items and
    a city-filter pill bar without extra API calls.
    """
    def create_option(self, name, value, label, selected, index, **kwargs):
        option = super().create_option(name, value, label, selected, index, **kwargs)
        try:
            row = self._acc_data.get(int(str(value)))
            if row:
                option['attrs'].update(row)
        except (TypeError, ValueError, AttributeError):
            pass
        return option


class ContractForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-input'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    end_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-input'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    last_sale_datetime = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-input'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    last_sync_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-input'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
    )

    class Meta:
        model  = Contract
        fields = ['title', 'designation', 'account', 'start_date', 'end_date', 'status',
                  'last_sale_datetime', 'last_sync_at']
        widgets = {
            'designation': forms.Textarea(attrs={'rows': 3, 'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['status'].widget.attrs['class'] = 'form-input'

        # Replace the account widget with AccountSelect so each <option> carries
        # data-name / data-code / data-city for the JS city-filter dropdown.
        acc_qs = Account.objects.order_by("name")
        acc_widget = AccountSelect(attrs={'class': 'form-input'})
        acc_widget._acc_data = {
            a.pk: {'data-name': a.name, 'data-code': a.code, 'data-city': a.city}
            for a in acc_qs
        }
        self.fields['account'].widget = acc_widget
        self.fields['account'].queryset = acc_qs

        # Pre-format datetimes for the datetime-local input
        if self.instance and self.instance.pk:
            if self.instance.start_date:
                self.initial['start_date'] = self.instance.start_date.strftime('%Y-%m-%dT%H:%M')
            if self.instance.end_date:
                self.initial['end_date'] = self.instance.end_date.strftime('%Y-%m-%dT%H:%M')


class ContractProductForm(forms.ModelForm):
    class Meta:
        model  = Contract_Product
        fields = ['product', 'external_designation', 'points_per_unit', 'target_quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-input'}),
            'external_designation': forms.TextInput(attrs={
                'class': 'form-input',
                'autocomplete': 'off',
                'placeholder': 'e.g. DOLI1000',
            }),
            'points_per_unit': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '1',
                'placeholder': '1',
            }),
            'target_quantity': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'placeholder': 'e.g. 100',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.available_products = kwargs.pop('available_products', None)
        super().__init__(*args, **kwargs)
        base_qs = (
            self.available_products
            if self.available_products is not None
            else Product.objects.filter(status='active')
        )
        if self.instance and self.instance.pk:
            # Existing row — always include the currently linked product so it
            # renders correctly even if it has since been deactivated or re-linked.
            qs = (
                base_qs | Product.objects.filter(pk=self.instance.product_id)
            ).distinct().order_by('designation')
        else:
            qs = base_qs.order_by('designation')

        self.fields['product'].queryset = qs
        self.fields['product'].label_from_instance = lambda obj: (
            f"{obj.designation} [Inactive]" if obj.status == "inactive" else obj.designation
        )

    def validate_unique(self):
        skip_pks = getattr(self.instance, '_skip_unique_pks', None)
        if not skip_pks:
            return super().validate_unique()
        # Re-run unique_together checks manually, excluding rows being deleted
        exclude = self._get_validation_exclusions()
        unique_checks, _ = self.instance._get_unique_checks(exclude=exclude)
        errors = {}
        for model_class, unique_check in unique_checks:
            lookup, ok = {}, True
            for fn in unique_check:
                val = getattr(self.instance, model_class._meta.get_field(fn).attname)
                if val is None:
                    ok = False
                    break
                lookup[fn] = val
            if not ok or len(unique_check) != len(lookup):
                continue
            qs = model_class._default_manager.filter(**lookup).exclude(pk__in=skip_pks)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                errors.setdefault(NON_FIELD_ERRORS, []).append(
                    self.instance.unique_error_message(model_class, unique_check)
                )
        if errors:
            self._update_errors(ValidationError(errors))


class ContractProductFormSetBase(BaseInlineFormSet):
    def full_clean(self):
        # Before validation runs, find which existing rows are being deleted and
        # annotate new (extra) form instances so their uniqueness checks can skip them.
        if self.is_bound:
            freed_cp_pks = {
                f.instance.pk
                for f in self.initial_forms
                if f.instance.pk and self.data.get(f'{f.prefix}-DELETE')
            }
            if freed_cp_pks:
                for f in self.extra_forms:
                    f.instance._skip_unique_pks = freed_cp_pks
        super().full_clean()


ContractProductFormSet = inlineformset_factory(
    Contract,
    Contract_Product,
    form=ContractProductForm,
    formset=ContractProductFormSetBase,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

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

    def save(self, actor=None) -> User:
        """
        Persist the user, their type flags, groups, and UserProfile.

        Pass actor=request.user from the view so traceability fields on
        UserProfile are stamped at creation / update time.
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
            # Use update_or_create so the account is set atomically on first INSERT.
            # get_or_create(user=user) without defaults would try to INSERT a row
            # with only user set, hitting the NOT NULL constraint on account_id.
            defaults = {"account": data["account"]}
            if actor:
                # On edit, always stamp modified_by; on create, also stamp created_by.
                existing = UserProfile.objects.filter(user=user).exists()
                if existing:
                    defaults["modified_by"] = actor
                else:
                    defaults["created_by"] = actor
            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults=defaults,
            )
            # email_verified is managed by the portal flow — update_or_create never touches it
        else:
            UserProfile.objects.filter(user=user).delete()

        return user


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class ProductForm(forms.ModelForm):
    class Meta:
        model  = Product
        fields = ['code', 'designation', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['designation'].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['status'].widget.attrs.update({'class': 'form-input'})

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        qs = Product.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A product with this code already exists.')
        return code


# ---------------------------------------------------------------------------
# API Tokens
# ---------------------------------------------------------------------------

class TokenForm(forms.ModelForm):

    class Meta:
        model  = APIToken
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.update({
            'class': 'form-input',
            'autocomplete': 'off',
            'placeholder': 'e.g. Pharmacy SAADA Sync Client',
        })


# ---------------------------------------------------------------------------
# Configuration — Social Applications
# ---------------------------------------------------------------------------

class SocialAppForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        provider_choices = [("", "— Select provider —")] + [
            (pid, pid.title())
            for pid in sorted(allauth_providers.registry.provider_map.keys())
        ]
        self.fields["provider"].widget = forms.Select(choices=provider_choices, attrs={"class": "form-input"})
        self.fields["name"].widget.attrs.update({"class": "form-input", "placeholder": "e.g. Google"})
        self.fields["client_id"].widget.attrs.update({"class": "form-input", "placeholder": "OAuth Client ID"})
        self.fields["secret"].widget.attrs.update({"class": "form-input", "placeholder": "OAuth Client Secret"})
        self.fields["key"].widget.attrs.update({"class": "form-input", "placeholder": "Optional API key"})
        self.fields["provider_id"].widget.attrs.update({"class": "form-input", "placeholder": "Optional (leave blank)"})
        self.fields["sites"].widget.attrs.update({"class": "form-input", "size": "4"})
        self.fields["sites"].queryset = Site.objects.all()
        self.fields["secret"].required = False

    class Meta:
        model  = SocialApp
        fields = ["provider", "name", "client_id", "secret", "key", "provider_id", "sites"]
        labels = {
            "provider_id": "Provider ID",
            "client_id":   "Client ID",
        }


# ---------------------------------------------------------------------------
# Configuration — Sites
# ---------------------------------------------------------------------------

class SiteForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["domain"].widget.attrs.update({"class": "form-input", "placeholder": "e.g. example.com"})
        self.fields["name"].widget.attrs.update({"class": "form-input", "placeholder": "e.g. FIDPHA"})

    class Meta:
        model  = Site
        fields = ["domain", "name"]
        labels = {"name": "Display Name"}
