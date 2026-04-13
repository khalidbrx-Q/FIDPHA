from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from unfold.admin import ModelAdmin
from .models import APIToken


@admin.register(APIToken)
class APITokenAdmin(ModelAdmin):
    list_display = ["name", "masked_token_display", "is_active", "usage_count", "last_used_at", "created_at", "copy_button"]
    list_filter = ["is_active"]
    readonly_fields = ["token_display", "masked_token_display", "created_at", "last_used_at", "usage_count"]
    search_fields = ["name"]
    ordering = ["-created_at"]

    fieldsets = [
        ("Token Info", {"fields": ["name", "is_active"]}),
        ("Token Key", {"fields": ["token_display"]}),
        ("Usage", {"fields": ["usage_count", "last_used_at", "created_at"]}),
    ]

    def token_display(self, obj):
        if obj.pk:
            return format_html(
                '<div style="display:flex; align-items:center; gap:10px;">'
                '<code style="background:#0f172a; color:#22c55e; padding:8px 14px; border-radius:6px; font-size:0.85rem;">{}</code>'
                '<button type="button" onclick="navigator.clipboard.writeText(\'{}\'); this.textContent=\'Copied!\'; setTimeout(()=>this.textContent=\'Copy\',2000);" '
                'style="padding:6px 14px; background:#1b679b; color:white; border:none; border-radius:6px; cursor:pointer; font-size:0.82rem;">Copy</button>'
                '</div>',
                obj.masked_token, obj.token
            )
        return format_html('<span style="color:#888;">Token will be shown after saving</span>')
    token_display.short_description = "Token"

    def masked_token_display(self, obj):
        return format_html(
            '<code style="font-size:0.82rem; color:#888;">{}...{}</code>',
            obj.token[:4], obj.token[-4:]
        )
    masked_token_display.short_description = "Token"

    def copy_button(self, obj):
        return format_html(
            '<button type="button" onclick="navigator.clipboard.writeText(\'{}\'); this.textContent=\'Copied!\'; setTimeout(()=>this.textContent=\'Copy\',2000);" '
            'style="padding:4px 12px; background:#1b679b; color:white; border:none; border-radius:6px; cursor:pointer; font-size:0.78rem;">Copy</button>',
            obj.token
        )
    copy_button.short_description = "Copy Token"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)