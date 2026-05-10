from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0006_backfill_sale_product_ppv"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="rejection_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
