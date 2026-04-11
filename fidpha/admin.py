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

    def product_count(self, obj):
        count = obj.contract_product_set.count()
        return format_html(
            '<span style="background-color: rgba(27,103,155,0.15); color: #1b679b; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{} product{}</span>',
            count, "s" if count != 1 else ""
        )

    product_count.short_description = "Products"
    can_delete = False
    show_change_link = False
    ordering = ["-start_date"]

    def has_add_permission(self, request, obj=None):
        return False

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
    extra = 1
    classes = ["collapse"]
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
    list_display = ["code", "designation", "status"]
    list_filter = ["status"]
    list_editable = ["status"]
    search_fields = ["code", "designation"]
    ordering = ["designation"]
    list_per_page = 20

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
# -----------------------
# Contract Admin
# -----------------------
@admin.register(Contract)
class ContractAdmin(ModelAdmin):
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
            '<span style="background-color: rgba(27,103,155,0.15); color: #1b679b; font-size: 0.75rem; padding: 2px 10px; border-radius: 20px; font-weight: 600;">{} product{}</span>',
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

admin.site.site_header = "FIDPHA Administration"
admin.site.site_title = "FIDPHA Admin"
admin.site.index_title = "Welcome to FIDPHA"