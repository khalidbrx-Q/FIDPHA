from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0002_alter_systemconfig_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemconfig",
            name="max_batch_size",
            field=models.PositiveIntegerField(
                default=50000,
                help_text="Maximum sale rows accepted per API batch (1–100,000).",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="ppv_tolerance_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Reject rows where submitted PPV deviates more than this % "
                    "from the catalogue PPV. Leave blank to disable."
                ),
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="rejection_rate_warn_threshold",
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text="Rejection rate % above which a yellow warning badge is shown (1–99).",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="rejection_rate_danger_threshold",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="Rejection rate % above which a red danger badge is shown (must exceed warn threshold).",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="api_token_rate_limit",
            field=models.PositiveIntegerField(
                default=1000,
                help_text="Maximum API requests per token per hour (1–10,000).",
            ),
        ),
    ]
