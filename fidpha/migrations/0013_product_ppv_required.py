from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fidpha', '0012_account_auto_review_enabled'),
    ]

    operations = [
        # Any product with NULL ppv gets 0.00 as a safe fallback before the constraint is applied.
        migrations.RunSQL(
            "UPDATE Product SET ppv = 0.00 WHERE ppv IS NULL",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='product',
            name='ppv',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]
