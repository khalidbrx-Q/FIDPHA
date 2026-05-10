from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fidpha", "0011_roleprofile_traceability"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="auto_review_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
