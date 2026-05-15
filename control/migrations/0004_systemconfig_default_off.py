"""
Set the default sentinel value for all new configurable fields to 0 (disabled /
no-limit / unlimited) instead of the old hardcoded values, and reset the existing
singleton row (pk=1) so the page opens with everything toggled OFF by default.
"""

from django.db import migrations, models


def reset_existing_row(apps, schema_editor):
    """Push the existing SystemConfig singleton to all-disabled defaults."""
    SystemConfig = apps.get_model("control", "SystemConfig")
    SystemConfig.objects.filter(pk=1).update(
        max_batch_size=0,
        ppv_tolerance_percent=None,
        rejection_rate_warn_threshold=0,
        rejection_rate_danger_threshold=0,
        api_token_rate_limit=0,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0003_systemconfig_new_fields"),
    ]

    operations = [
        # Update column defaults so new rows also start all-off
        migrations.AlterField(
            model_name="systemconfig",
            name="max_batch_size",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Maximum sale rows accepted per API batch (1–100,000). 0 = no limit.",
            ),
        ),
        migrations.AlterField(
            model_name="systemconfig",
            name="rejection_rate_warn_threshold",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Rejection rate % above which a yellow warning badge is shown (1–99). 0 = disabled.",
            ),
        ),
        migrations.AlterField(
            model_name="systemconfig",
            name="rejection_rate_danger_threshold",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Rejection rate % above which a red danger badge is shown (must exceed warn threshold). 0 = disabled.",
            ),
        ),
        migrations.AlterField(
            model_name="systemconfig",
            name="api_token_rate_limit",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Maximum API requests per token per hour (1–10,000). 0 = unlimited.",
            ),
        ),
        # Reset the existing singleton row
        migrations.RunPython(reset_existing_row, migrations.RunPython.noop),
    ]
