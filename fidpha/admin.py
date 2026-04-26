"""
fidpha/admin.py
---------------
Django admin registration for the fidpha app.

This file is responsible only for configuring the admin panel UI:
model registration, inline classes, display columns, search, filters,
and form customisation. It uses the django-unfold theme throughout.

Admin-specific AJAX helper endpoints (product toggle, available products,
add contract product) have been moved to fidpha/admin_api.py to keep
this file focused on admin panel configuration only.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.forms import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django import forms
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from .models import Account, UserProfile, Product, Contract, Contract_Product


# -----------------------
# Account Form
# -----------------------
class AccountAdminForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].help_text = format_html(
            '''
            <button type="button" 
                onclick="document.getElementById('id_code').value = 'PH-' + Math.random().toString(36).substring(2, 8).toUpperCase();"
                style="margin-top: 8px; 
                       padding: 6px 14px; 
                       cursor: pointer; 
                       background-color: #1b679b; 
                       color: white; 
                       border: none; 
                       border-radius: 6px; 
                       font-size: 0.85rem;
                       font-weight: 600;">
                ⚡ Generate Code
            </button>
            '''
        )


# -----------------------
# Inlines
# -----------------------
class UserProfileInline(StackedInline):
    model = UserProfile
    fk_name = "user"
    can_delete = False
    verbose_name = "Account"
    verbose_name_plural = "Account"
    autocomplete_fields = ["account"]
    readonly_fields = ["account_details"]

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["account"]
        return ["account", "account_details"]

    def account_details(self, obj):
        if obj and obj.pk and obj.account:
            account = obj.account
            status_color = "#22c55e" if account.status == "active" else "#ef4444"
            portal_color = "#22c55e" if account.pharmacy_portal else "#ef4444"
            return format_html(
                '''
                <table style="font-size: 0.85rem; width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888; width: 140px;">Code</td>
                        <td style="padding: 5px 0; font-weight: 600;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">City</td>
                        <td style="padding: 5px 0;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Phone</td>
                        <td style="padding: 5px 0;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Email</td>
                        <td style="padding: 5px 0;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Status</td>
                        <td style="padding: 5px 0;">
                            <span style="background-color: {}20; color: {}; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Portal Access</td>
                        <td style="padding: 5px 0;">
                            <span style="background-color: {}20; color: {}; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Active Contracts</td>
                        <td style="padding: 5px 0; font-weight: 600;">{}</td>
                    </tr>
                </table>
                ''',
                account.code,
                account.city,
                account.phone,
                account.email,
                status_color, status_color, account.status.capitalize(),
                portal_color, portal_color, "Enabled" if account.pharmacy_portal else "Disabled",
                account.contracts.filter(status="active").count(),
            )
        return format_html('<span style="color: #888;">—</span>')

    account_details.short_description = "Account Details"

    def get_min_num(self, request, obj=None, **kwargs):
        if obj and obj.is_staff:
            return 0
        return 1

    def get_extra(self, request, obj=None, **kwargs):
        if obj and obj.is_staff:
            return 0
        return 1

    def get_max_num(self, request, obj=None, **kwargs):
        if obj and obj.is_staff:
            return 0
        return 1

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        is_staff = request.POST.get("is_staff") == "on"
        if (obj and obj.is_staff) or is_staff:
            for field in formset.form.base_fields.values():
                field.required = False
        return formset


class UserProfileAccountFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                user = form.cleaned_data.get("user")
                if user:
                    account_id = self.instance.pk
                    already_linked = UserProfile.objects.filter(user=user).exclude(account_id=account_id).exists()
                    if already_linked:
                        raise ValidationError(f"User '{user.username}' is already linked to another account.")


class UserProfileAccountInline(TabularInline):
    model = UserProfile
    fk_name = "account"
    extra = 1
    verbose_name = "Available User"
    verbose_name_plural = "Available Users"
    autocomplete_fields = ["user"]
    formset = UserProfileAccountFormSet
    fields = ["user"]


class ContractAccountInline(TabularInline):
    model = Contract
    extra = 0
    verbose_name = "Contract"
    verbose_name_plural = "Contracts"
    fields = ["contract_link", "contract_status", "start_date", "end_date", "product_count"]
    readonly_fields = ["contract_link", "contract_status", "start_date", "end_date", "product_count"]
    can_delete = False
    show_change_link = False
    ordering = ["-start_date"]

    def has_add_permission(self, request, obj=None):
        return False

    def product_count(self, obj):
        count = obj.contract_product_set.count()
        return format_html(
            '<span style="background-color: rgba(27,103,155,0.15); color: #1b679b; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{} product{}</span>',
            count, "s" if count != 1 else ""
        )
    product_count.short_description = "Products"

    def contract_link(self, obj):
        return format_html(
            '<a href="/admin/fidpha/contract/{}/change/" style="color: #1b679b; font-weight: 600;">{}</a>',
            obj.pk, obj.title
        )
    contract_link.short_description = "Title"

    def contract_status(self, obj):
        if obj.status == "active":
            return format_html(
                '<span style="background-color: rgba(34,197,94,0.15); color: #22c55e; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">✓ Active</span>'
            )
        else:
            return format_html(
                '<span style="background-color: rgba(239,68,68,0.15); color: #ef4444; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">✗ Inactive</span>'
            )
    contract_status.short_description = "Status"


class ContractProductInline(TabularInline):
    model = Contract_Product
    extra = 0  # change from 1 to 0 to remove empty row
    verbose_name = "Product"
    verbose_name_plural = "Products"
    autocomplete_fields = ["product"]


# -----------------------
# User Admin
# -----------------------
class UserAdmin(BaseUserAdmin, ModelAdmin):
    class Media:
        js = ["admin/user_form.js"]

    inlines = [UserProfileInline]
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["username", "email", "first_name", "last_name"]

    add_fieldsets = [
        ("Login Info",    {"fields": ["username", "password1", "password2"]}),
        ("Personal Info", {"fields": ["first_name", "last_name", "email"]}),
        ("Permissions",   {"fields": ["is_active", "is_staff"]}),
    ]

    fieldsets = [
        ("Login Info",      {"fields": ["username", "password"]}),
        ("Personal Info",   {"fields": ["first_name", "last_name", "email", "email_verification_status"]}),
        ("Permissions",     {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Important dates", {"fields": ["last_login", "date_joined"]}),
    ]

    readonly_fields = ["email_verification_status"]

    def email_verification_status(self, obj):
        try:
            if obj.profile.email_verified:
                return format_html(
                    '<span style="background-color: rgba(34,197,94,0.15); color: #22c55e; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">✓ Email Verified</span>'
                )
            else:
                return format_html(
                    '<span style="background-color: rgba(245,158,11,0.15); color: #f59e0b; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">⚠ Email Not Verified</span>'
                )
        except:
            return format_html('<span style="color: #888;">—</span>')

    email_verification_status.short_description = "Email Status"

    def get_inlines(self, request, obj=None):
        return self.inlines

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if "autocomplete" in request.path:
            already_linked = UserProfile.objects.values_list("user_id", flat=True)
            account_id = request.GET.get("forward", None)
            if account_id:
                already_linked = already_linked.exclude(account_id=account_id)
            queryset = queryset.exclude(id__in=already_linked).exclude(is_staff=True)
        return queryset, use_distinct

    def delete_model(self, request, obj):
        try:
            from allauth.socialaccount.models import SocialAccount
            SocialAccount.objects.filter(user=obj).delete()
        except:
            pass
        try:
            from allauth.account.models import EmailAddress
            EmailAddress.objects.filter(user=obj).delete()
        except:
            pass
        try:
            obj.profile.delete()
        except:
            pass
        obj.delete()

    def delete_queryset(self, request, queryset):
        from allauth.socialaccount.models import SocialAccount
        from allauth.account.models import EmailAddress
        for user in queryset:
            try:
                SocialAccount.objects.filter(user=user).delete()
            except:
                pass
            try:
                EmailAddress.objects.filter(user=user).delete()
            except:
                pass
            try:
                user.profile.delete()
            except:
                pass
            user.delete()


# -----------------------
# Account Admin
# -----------------------
@admin.register(Account)
class AccountAdmin(ModelAdmin):
    form = AccountAdminForm
    inlines = [UserProfileAccountInline, ContractAccountInline]
    list_display = ["code", "name", "city", "phone", "email", "pharmacy_portal", "status", "contract_count", "user_count"]
    list_filter = ["status", "city", "pharmacy_portal"]
    list_editable = ["status", "pharmacy_portal"]
    search_fields = ["code", "name", "city", "email", "phone"]
    ordering = ["name"]
    list_per_page = 20
    fieldsets = [
        ("General Info", {"fields": ["code", "name", "status"]}),
        ("Location",     {"fields": ["city", "location"]}),
        ("Contact",      {"fields": ["phone", "email"]}),
        ("Portal",       {"fields": ["pharmacy_portal"]}),
    ]

    @admin.display(description="Contracts")
    def contract_count(self, obj):
        count = obj.contracts.count()
        return format_html(
            '<a href="/admin/fidpha/contract/?account__id__exact={}" style="color: #1b679b; font-weight: 600;">{} contract{}</a>',
            obj.pk, count, "s" if count != 1 else ""
        )

    @admin.display(description="Users")
    def user_count(self, obj):
        return obj.users.count()


# -----------------------
# Product Admin
# -----------------------
@admin.register(Product)
class ProductAdmin(ModelAdmin):
    class Media:
        js = ["admin/product_toggle.js", "admin/product_list.js"]

    list_display = ["code", "designation", "status_toggle", "active_contracts_count"]
    list_filter = ["status"]
    search_fields = ["code", "designation"]
    ordering = ["designation"]
    list_per_page = 20
    actions = ["activate_products", "deactivate_products"]

    @admin.action(description="✓ Activate selected products")
    def activate_products(self, request, queryset):
        count = queryset.update(status="active")
        self.message_user(request, f"{count} product(s) activated successfully.")

    @admin.action(description="✗ Deactivate selected products")
    def deactivate_products(self, request, queryset):
        blocked = []
        deactivated = 0
        for product in queryset:
            active_contracts = Contract.objects.filter(
                contract_product__product=product,
                status="active"
            )
            if active_contracts.exists():
                contract_titles = ", ".join(active_contracts.values_list("title", flat=True))
                blocked.append(f"{product.designation} ({contract_titles})")
            else:
                product.status = "inactive"
                product.save()
                deactivated += 1

        if deactivated:
            self.message_user(request, f"{deactivated} product(s) deactivated successfully.")
        if blocked:
            self.message_user(
                request,
                f"Skipped — linked to active contracts: {' | '.join(blocked)}",
                level="warning"
            )

    @admin.display(description="Active Contracts")
    def active_contracts_count(self, obj):
        count = Contract.objects.filter(
            contract_product__product=obj,
            status="active"
        ).count()
        if count == 0:
            return format_html(
                '<span style="background-color: rgba(34,197,94,0.15); color: #22c55e; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">0</span>'
            )
        else:
            return format_html(
                '<span style="background-color: rgba(239,68,68,0.15); color: #ef4444; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{}</span>',
                count
            )

    def status_toggle(self, obj):
        if obj.status == "active":
            return format_html(
                '<button type="button" '
                'onclick="toggleProductStatus({}, \'inactive\')" '
                'style="background-color: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); padding: 4px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; cursor: pointer;">'
                '✓ Active</button>',
                obj.pk
            )
        else:
            return format_html(
                '<button type="button" '
                'onclick="toggleProductStatus({}, \'active\')" '
                'style="background-color: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); padding: 4px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; cursor: pointer;">'
                '✗ Inactive</button>',
                obj.pk
            )
    status_toggle.short_description = "Status"

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if "autocomplete" in request.path:
            import re
            queryset = queryset.filter(status="active")
            referer = request.META.get("HTTP_REFERER", "")
            match = re.search(r"/contract/(\d+)/change/", referer)
            if match:
                contract_id = match.group(1)
                already_linked = Contract_Product.objects.filter(
                    contract_id=contract_id
                ).values_list("product_id", flat=True)
                queryset = queryset.exclude(id__in=already_linked)
        return queryset, use_distinct

    @admin.action(description="🗑 Delete selected products")
    def delete_products(self, request, queryset):
        blocked = []
        deleted = 0
        for product in queryset:
            active_contracts = Contract.objects.filter(
                contract_product__product=product,
                status="active"
            )
            if active_contracts.exists():
                contract_titles = ", ".join(active_contracts.values_list("title", flat=True))
                blocked.append(f"{product.designation} ({contract_titles})")
            else:
                product.delete()
                deleted += 1

        if deleted:
            self.message_user(request, f"{deleted} product(s) deleted successfully.")
        if blocked:
            self.message_user(
                request,
                f"Cannot delete — linked to active contracts: {' | '.join(blocked)}",
                level="warning"
            )
# -----------------------
# Contract Admin
# -----------------------
@admin.register(Contract)
class ContractAdmin(ModelAdmin):
    class Media:
        js = ["admin/contract_form.js"]

    inlines = [ContractProductInline]
    list_display = ["title", "account", "get_account_city", "start_date", "end_date", "status", "product_count"]
    list_filter = ["status", "account"]
    list_editable = ["status"]
    search_fields = ["title", "designation", "account__name"]
    autocomplete_fields = ["account"]
    ordering = ["-start_date"]
    list_per_page = 20
    fieldsets = [
        ("General Info", {"fields": ["title", "designation", "status"]}),
        ("Account",      {"fields": ["account", "account_info"]}),
        ("Duration",     {"fields": ["start_date", "end_date"]}),
    ]
    readonly_fields = ["account_info"]

    @admin.display(description="Products")
    def product_count(self, obj):
        count = obj.contract_product_set.count()
        return format_html(
            '<span style="background-color: rgba(27,103,155,0.15); color: #1b679b; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600; white-space: nowrap;">{} product{}</span>',
            count, "s" if count != 1 else ""
        )

    def account_info(self, obj):
        if obj and obj.account:
            account = obj.account
            status_color = "#22c55e" if account.status == "active" else "#ef4444"
            portal_color = "#22c55e" if account.pharmacy_portal else "#ef4444"
            return format_html(
                '''
                <table style="font-size: 0.85rem; width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888; width: 140px;">Code</td>
                        <td style="padding: 5px 0; font-weight: 600;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Name</td>
                        <td style="padding: 5px 0;">
                            <a href="/admin/fidpha/account/{}/change/" style="color: #1b679b; font-weight: 600;">{}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">City</td>
                        <td style="padding: 5px 0;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Phone</td>
                        <td style="padding: 5px 0;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Email</td>
                        <td style="padding: 5px 0;">{}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Status</td>
                        <td style="padding: 5px 0;">
                            <span style="background-color: {}20; color: {}; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 10px 5px 0; color: #888;">Portal Access</td>
                        <td style="padding: 5px 0;">
                            <span style="background-color: {}20; color: {}; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{}</span>
                        </td>
                    </tr>
                </table>
                ''',
                account.code,
                account.pk, account.name,
                account.city,
                account.phone,
                account.email,
                status_color, status_color, account.status.capitalize(),
                portal_color, portal_color, "Enabled" if account.pharmacy_portal else "Disabled",
            )
        return format_html('<span style="color: #888;">—</span>')

    account_info.short_description = "Account Details"

    @admin.display(description="City")
    def get_account_city(self, obj):
        return obj.account.city


# -----------------------
# Contract_Product Admin
# -----------------------
@admin.register(Contract_Product)
class ContractProductAdmin(ModelAdmin):
    list_display = ["contract", "product", "external_designation"]
    search_fields = ["contract__title", "product__designation", "external_designation"]
    list_filter = ["contract", "product"]
    autocomplete_fields = ["contract", "product"]
    ordering = ["contract"]
    list_per_page = 20


# -----------------------
# Register & Site Config
# -----------------------
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.site_header = "WinInPharma Administration"
admin.site.site_title = "WinInPharma Admin"
admin.site.index_title = "Welcome to WinInPharma"