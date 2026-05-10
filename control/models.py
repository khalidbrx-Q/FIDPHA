from django.conf import settings
from django.db import models


class SystemConfig(models.Model):
    """Single-row system configuration table (always pk=1)."""
    auto_review_enabled    = models.BooleanField(default=False)
    auto_review_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    auto_review_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "SystemConfig"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
