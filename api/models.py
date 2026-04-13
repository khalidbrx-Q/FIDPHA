
import secrets
from django.db import models


class APIToken(models.Model):
    name = models.CharField(max_length=100, help_text="Description of who this token is for")
    token = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "API Token"
        verbose_name_plural = "API Tokens"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Revoked'})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def regenerate(self):
        self.token = secrets.token_hex(32)
        self.save()

    @property
    def masked_token(self):
        return f"••••••••••••••••••••••••••••{self.token[-4:]}"

