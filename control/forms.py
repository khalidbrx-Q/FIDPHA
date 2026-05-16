# -*- coding: utf-8 -*-
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

import re

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

# Single source of truth for phone-prefix data.
# Format: (dial_prefix, ISO_3166-1_alpha-2_UPPERCASE, max_local_digits)
# Morocco first (default).  The JS flag-picker sorts the rest by translated name.
# max_local_digits must mirror JS RAW[].maxLen — both are derived from this list.
_PHONE_DATA = [
    # (prefix,  ISO,  max_digits)
    ('+212', 'MA',  9),   # Morocco (default — always first)
    ('+1',   'US', 10),   # USA / Canada (NANP)
    ('+7',   'RU', 10),   # Russia / Kazakhstan
    ('+20',  'EG', 10),   # Egypt
    ('+27',  'ZA',  9),   # South Africa
    ('+30',  'GR', 10),   # Greece
    ('+31',  'NL',  9),   # Netherlands
    ('+32',  'BE',  9),   # Belgium
    ('+33',  'FR',  9),   # France
    ('+34',  'ES',  9),   # Spain
    ('+36',  'HU',  9),   # Hungary
    ('+39',  'IT', 10),   # Italy
    ('+40',  'RO',  9),   # Romania
    ('+41',  'CH',  9),   # Switzerland
    ('+43',  'AT', 10),   # Austria
    ('+44',  'GB', 10),   # United Kingdom
    ('+45',  'DK',  8),   # Denmark
    ('+46',  'SE',  9),   # Sweden
    ('+47',  'NO',  8),   # Norway
    ('+48',  'PL',  9),   # Poland
    ('+49',  'DE', 11),   # Germany
    ('+51',  'PE',  9),   # Peru
    ('+52',  'MX', 10),   # Mexico
    ('+53',  'CU',  8),   # Cuba
    ('+54',  'AR', 10),   # Argentina
    ('+55',  'BR', 11),   # Brazil
    ('+56',  'CL',  9),   # Chile
    ('+57',  'CO', 10),   # Colombia
    ('+58',  'VE', 10),   # Venezuela
    ('+60',  'MY',  9),   # Malaysia
    ('+61',  'AU',  9),   # Australia
    ('+62',  'ID', 11),   # Indonesia
    ('+63',  'PH', 10),   # Philippines
    ('+64',  'NZ',  9),   # New Zealand
    ('+65',  'SG',  8),   # Singapore
    ('+66',  'TH',  9),   # Thailand
    ('+81',  'JP', 10),   # Japan
    ('+82',  'KR', 10),   # South Korea
    ('+84',  'VN',  9),   # Vietnam
    ('+86',  'CN', 11),   # China
    ('+90',  'TR', 10),   # Turkey
    ('+91',  'IN', 10),   # India
    ('+92',  'PK', 10),   # Pakistan
    ('+93',  'AF',  9),   # Afghanistan
    ('+94',  'LK',  9),   # Sri Lanka
    ('+95',  'MM',  9),   # Myanmar
    ('+98',  'IR', 10),   # Iran
    ('+213', 'DZ',  9),   # Algeria
    ('+216', 'TN',  8),   # Tunisia
    ('+218', 'LY',  9),   # Libya
    ('+220', 'GM',  7),   # Gambia
    ('+221', 'SN',  9),   # Senegal
    ('+222', 'MR',  8),   # Mauritania
    ('+223', 'ML',  8),   # Mali
    ('+224', 'GN',  9),   # Guinea
    ('+225', 'CI', 10),   # Ivory Coast
    ('+226', 'BF',  8),   # Burkina Faso
    ('+227', 'NE',  8),   # Niger
    ('+228', 'TG',  8),   # Togo
    ('+229', 'BJ',  8),   # Benin
    ('+230', 'MU',  8),   # Mauritius
    ('+231', 'LR',  9),   # Liberia
    ('+232', 'SL',  8),   # Sierra Leone
    ('+233', 'GH',  9),   # Ghana
    ('+234', 'NG', 10),   # Nigeria
    ('+235', 'TD',  8),   # Chad
    ('+236', 'CF',  8),   # Central African Republic
    ('+237', 'CM',  9),   # Cameroon
    ('+238', 'CV',  7),   # Cape Verde
    ('+239', 'ST',  7),   # São Tomé and Príncipe
    ('+240', 'GQ',  9),   # Equatorial Guinea
    ('+241', 'GA',  7),   # Gabon
    ('+242', 'CG',  9),   # Republic of the Congo
    ('+243', 'CD',  9),   # DR Congo
    ('+244', 'AO',  9),   # Angola
    ('+245', 'GW',  9),   # Guinea-Bissau
    ('+248', 'SC',  7),   # Seychelles
    ('+249', 'SD',  9),   # Sudan
    ('+250', 'RW',  9),   # Rwanda
    ('+251', 'ET',  9),   # Ethiopia
    ('+252', 'SO',  9),   # Somalia
    ('+253', 'DJ',  8),   # Djibouti
    ('+254', 'KE',  9),   # Kenya
    ('+255', 'TZ',  9),   # Tanzania
    ('+256', 'UG',  9),   # Uganda
    ('+257', 'BI',  8),   # Burundi
    ('+258', 'MZ',  9),   # Mozambique
    ('+260', 'ZM',  9),   # Zambia
    ('+261', 'MG',  9),   # Madagascar
    ('+262', 'RE',  9),   # Réunion
    ('+263', 'ZW',  9),   # Zimbabwe
    ('+264', 'NA',  9),   # Namibia
    ('+265', 'MW',  9),   # Malawi
    ('+266', 'LS',  8),   # Lesotho
    ('+267', 'BW',  8),   # Botswana
    ('+268', 'SZ',  8),   # Eswatini
    ('+269', 'KM',  7),   # Comoros
    ('+291', 'ER',  7),   # Eritrea
    ('+297', 'AW',  7),   # Aruba
    ('+298', 'FO',  6),   # Faroe Islands
    ('+299', 'GL',  6),   # Greenland
    ('+350', 'GI',  8),   # Gibraltar
    ('+351', 'PT',  9),   # Portugal
    ('+352', 'LU',  9),   # Luxembourg
    ('+353', 'IE',  9),   # Ireland
    ('+354', 'IS',  7),   # Iceland
    ('+355', 'AL',  9),   # Albania
    ('+356', 'MT',  8),   # Malta
    ('+357', 'CY',  8),   # Cyprus
    ('+358', 'FI', 10),   # Finland
    ('+359', 'BG',  9),   # Bulgaria
    ('+370', 'LT',  8),   # Lithuania
    ('+371', 'LV',  8),   # Latvia
    ('+372', 'EE',  8),   # Estonia
    ('+373', 'MD',  8),   # Moldova
    ('+374', 'AM',  8),   # Armenia
    ('+375', 'BY',  9),   # Belarus
    ('+376', 'AD',  6),   # Andorra
    ('+377', 'MC',  8),   # Monaco
    ('+378', 'SM', 10),   # San Marino
    ('+380', 'UA',  9),   # Ukraine
    ('+381', 'RS',  9),   # Serbia
    ('+382', 'ME',  8),   # Montenegro
    ('+383', 'XK',  8),   # Kosovo
    ('+385', 'HR',  9),   # Croatia
    ('+386', 'SI',  8),   # Slovenia
    ('+387', 'BA',  8),   # Bosnia and Herzegovina
    ('+389', 'MK',  8),   # North Macedonia
    ('+420', 'CZ',  9),   # Czech Republic
    ('+421', 'SK',  9),   # Slovakia
    ('+423', 'LI',  7),   # Liechtenstein
    ('+501', 'BZ',  7),   # Belize
    ('+502', 'GT',  8),   # Guatemala
    ('+503', 'SV',  8),   # El Salvador
    ('+504', 'HN',  8),   # Honduras
    ('+505', 'NI',  8),   # Nicaragua
    ('+506', 'CR',  8),   # Costa Rica
    ('+507', 'PA',  8),   # Panama
    ('+509', 'HT',  8),   # Haiti
    ('+590', 'GP',  9),   # Guadeloupe
    ('+591', 'BO',  8),   # Bolivia
    ('+592', 'GY',  7),   # Guyana
    ('+593', 'EC',  9),   # Ecuador
    ('+595', 'PY',  9),   # Paraguay
    ('+597', 'SR',  7),   # Suriname
    ('+598', 'UY',  8),   # Uruguay
    ('+670', 'TL',  8),   # Timor-Leste
    ('+673', 'BN',  7),   # Brunei
    ('+675', 'PG',  8),   # Papua New Guinea
    ('+676', 'TO',  7),   # Tonga
    ('+677', 'SB',  7),   # Solomon Islands
    ('+678', 'VU',  7),   # Vanuatu
    ('+679', 'FJ',  7),   # Fiji
    ('+680', 'PW',  7),   # Palau
    ('+685', 'WS',  7),   # Samoa
    ('+686', 'KI',  8),   # Kiribati
    ('+688', 'TV',  6),   # Tuvalu
    ('+689', 'PF',  6),   # French Polynesia
    ('+691', 'FM',  7),   # Micronesia
    ('+692', 'MH',  7),   # Marshall Islands
    ('+850', 'KP', 10),   # North Korea
    ('+852', 'HK',  8),   # Hong Kong
    ('+853', 'MO',  8),   # Macau
    ('+855', 'KH',  9),   # Cambodia
    ('+856', 'LA',  9),   # Laos
    ('+880', 'BD', 10),   # Bangladesh
    ('+886', 'TW',  9),   # Taiwan
    ('+960', 'MV',  7),   # Maldives
    ('+961', 'LB',  8),   # Lebanon
    ('+962', 'JO',  9),   # Jordan
    ('+963', 'SY',  9),   # Syria
    ('+964', 'IQ', 10),   # Iraq
    ('+965', 'KW',  8),   # Kuwait
    ('+966', 'SA',  9),   # Saudi Arabia
    ('+967', 'YE',  9),   # Yemen
    ('+968', 'OM',  8),   # Oman
    ('+970', 'PS',  9),   # Palestine
    ('+971', 'AE',  9),   # UAE
    ('+972', 'IL',  9),   # Israel
    ('+973', 'BH',  8),   # Bahrain
    ('+974', 'QA',  8),   # Qatar
    ('+975', 'BT',  8),   # Bhutan
    ('+976', 'MN',  8),   # Mongolia
    ('+977', 'NP', 10),   # Nepal
    ('+992', 'TJ',  9),   # Tajikistan
    ('+993', 'TM',  8),   # Turkmenistan
    ('+994', 'AZ',  9),   # Azerbaijan
    ('+995', 'GE',  9),   # Georgia
    ('+996', 'KG',  9),   # Kyrgyzstan
    ('+998', 'UZ',  9),   # Uzbekistan
]

# Derived from _PHONE_DATA — used by the AccountForm ChoiceField.
# The label is just the prefix; display is handled entirely by the JS flag-picker.
PHONE_PREFIXES   = [(p, p) for p, _, _ in _PHONE_DATA]

# Maximum local digits per prefix — server-side validation safety net.
# Must stay in sync with JS RAW[].maxLen (both derived from _PHONE_DATA).
PHONE_MAX_DIGITS = {p: ml for p, _, ml in _PHONE_DATA}


class AccountForm(forms.ModelForm):
    """
    Form for creating and editing pharmacy accounts.

    Uses ModelForm so Django's _post_clean() automatically calls the model's
    clean() method — which enforces the "cannot deactivate with active
    contracts" business rule — and surfaces it as a non-field error.

    Phone normalization: a separate phone_prefix selector is combined with
    the local phone number in clean() to produce a normalized E.164-style
    value (e.g., +212612345678) stored in Account.phone.
    """

    phone_prefix = forms.ChoiceField(
        choices=PHONE_PREFIXES,
        initial='+212',
        required=False,
    )

    class Meta:
        model  = Account
        fields = ['code', 'name', 'city', 'location', 'phone',
                  'email', 'pharmacy_portal', 'auto_review_enabled', 'status']
        widgets = {
            'location': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname in ['code', 'name', 'city', 'email']:
            self.fields[fname].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['phone'].widget.attrs.update({
            'class': 'form-input',
            'autocomplete': 'off',
            'placeholder': '6 12 34 56 78',
        })
        self.fields['phone_prefix'].widget.attrs.update({'class': 'form-input phone-prefix-select'})
        self.fields['location'].widget.attrs.update({'class': 'form-input'})
        self.fields['status'].widget.attrs.update({'class': 'form-input'})

        # When editing an existing account, split the stored phone number into
        # prefix + local part so both inputs are pre-populated correctly.
        stored_phone = (self.instance.phone if self.instance and self.instance.pk else '') or ''
        if stored_phone:
            detected_prefix = '+212'  # fallback default
            local = stored_phone
            for prefix, _ in PHONE_PREFIXES:
                if stored_phone.startswith(prefix):
                    detected_prefix = prefix
                    local = stored_phone[len(prefix):]
                    break
            # Strip leading trunk zero (e.g. Moroccan "0698…" → "698…")
            if local.startswith('0'):
                local = local[1:]
            self.fields['phone_prefix'].initial = detected_prefix
            self.initial['phone'] = local

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        qs = Account.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('An account with this code already exists.')
        return code

    def clean(self):
        cleaned = super().clean()
        prefix = cleaned.get('phone_prefix') or '+212'
        local  = (cleaned.get('phone') or '').strip()

        if local:
            # Remove formatting characters (spaces, dashes, dots, parens)
            local = re.sub(r'[\s\-.\(\)]', '', local)

            # If the user typed the full international number, strip the leading
            # prefix and re-apply the selected one so the two fields stay in sync.
            if local.startswith('+'):
                for p, _ in PHONE_PREFIXES:
                    if local.startswith(p):
                        local = local[len(p):]
                        break
                else:
                    # Unknown prefix — raise a clear validation error
                    raise forms.ValidationError(
                        _("Phone number prefix not recognised. "
                          "Select a country prefix from the list.")
                    )
                local = prefix + local
            else:
                # Strip a single leading zero (common Moroccan/French format: 0612…)
                if local.startswith('0'):
                    local = local[1:]
                local = prefix + local

            # Enforce digit-count limit for the selected country
            digits_only = re.sub(r'\D', '', local[len(prefix):])
            max_digits   = PHONE_MAX_DIGITS.get(prefix, 15)
            if len(digits_only) > max_digits:
                raise forms.ValidationError(
                    _("Phone number is too long for the selected country "
                      "(max %(max)d digits after the prefix).")
                    % {'max': max_digits}
                )

            cleaned['phone'] = local

        return cleaned


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
            else Product.objects.all()
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
            f"{obj.designation} [Inactive]" if obj.status == Product.STATUS_INACTIVE else obj.designation
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
                existing = UserProfile.objects.filter(user=user).exists()
                if existing:
                    defaults["modified_by"] = actor
                else:
                    defaults["created_by"] = actor
                    defaults["modified_by"] = actor
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
        fields = ['code', 'designation', 'ppv', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['designation'].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off'})
        self.fields['ppv'].widget.attrs.update({'class': 'form-input', 'autocomplete': 'off', 'placeholder': '0.00'})
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
