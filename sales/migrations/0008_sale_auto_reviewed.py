from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0007_sale_rejection_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="auto_reviewed",
            field=models.BooleanField(default=False),
        ),
    ]
