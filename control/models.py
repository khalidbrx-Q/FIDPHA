from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class SystemConfig(models.Model):
    """Single-row system configuration table (always pk=1)."""

    # ── Sales ingestion ────────────────────────────────────────────────────
    auto_review_enabled    = models.BooleanField(default=False)
    auto_review_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    auto_review_updated_at = models.DateTimeField(auto_now=True)

    max_batch_size = models.PositiveIntegerField(
        default=0,  # 0 = no limit (toggle OFF)
        help_text=_("Maximum sale rows accepted per API batch (1–100,000). 0 = no limit."),
    )
    ppv_tolerance_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text=_(
            "Reject rows where submitted PPV deviates more than this % "
            "from the catalogue PPV. Leave blank to disable."
        ),
    )

    # ── Review UI thresholds ───────────────────────────────────────────────
    rejection_rate_warn_threshold = models.PositiveSmallIntegerField(
        default=0,  # 0 = no badge (toggle OFF)
        help_text=_("Rejection rate % above which a yellow warning badge is shown (1–99). 0 = disabled."),
    )
    rejection_rate_danger_threshold = models.PositiveSmallIntegerField(
        default=0,  # 0 = no badge (toggle OFF)
        help_text=_("Rejection rate % above which a red danger badge is shown (must exceed warn threshold). 0 = disabled."),
    )

    # ── API throttling ─────────────────────────────────────────────────────
    api_token_rate_limit = models.PositiveIntegerField(
        default=0,  # 0 = unlimited (toggle OFF)
        help_text=_("Maximum API requests per token per hour (1–10,000). 0 = unlimited."),
    )

    class Meta:
        db_table = "SystemConfig"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def clean(self):
        """
        Validate all configurable thresholds.

        Zero is a valid "disabled / no-limit" sentinel for:
          - max_batch_size (0 = accept any size)
          - rejection_rate_*_threshold (0 = never show that badge)
          - api_token_rate_limit (0 = no rate limit)
        """
        errors = {}

        # max_batch_size: 0 = unlimited, or 1–100,000
        if self.max_batch_size is not None and self.max_batch_size != 0:
            if not (1 <= self.max_batch_size <= 100_000):
                errors["max_batch_size"] = _("Must be between 1 and 100,000, or 0 for no limit.")

        # ppv_tolerance_percent: None/blank = disabled; if set must be 0.01–100
        if self.ppv_tolerance_percent is not None:
            if not (0 < self.ppv_tolerance_percent <= 100):
                errors["ppv_tolerance_percent"] = _("Must be between 0.01 and 100.")

        warn   = self.rejection_rate_warn_threshold
        danger = self.rejection_rate_danger_threshold

        # Thresholds: 0 = disabled for that badge; 1–99 / 1–100 when active
        if warn is not None and warn != 0 and not (1 <= warn <= 99):
            errors["rejection_rate_warn_threshold"] = _("Must be between 1 and 99, or 0 to disable.")
        if danger is not None and danger != 0 and not (1 <= danger <= 100):
            errors["rejection_rate_danger_threshold"] = _("Must be between 1 and 100, or 0 to disable.")

        # Enforce warn < danger only when both are non-zero
        if (warn is not None and danger is not None
                and warn > 0 and danger > 0
                and "rejection_rate_danger_threshold" not in errors):
            if warn >= danger:
                errors["rejection_rate_danger_threshold"] = _(
                    "Danger threshold must be strictly greater than the warn threshold."
                )

        # api_token_rate_limit: 0 = unlimited, or 1–10,000
        if self.api_token_rate_limit is not None and self.api_token_rate_limit != 0:
            if not (1 <= self.api_token_rate_limit <= 10_000):
                errors["api_token_rate_limit"] = _("Must be between 1 and 10,000, or 0 for no limit.")

        if errors:
            raise ValidationError(errors)
