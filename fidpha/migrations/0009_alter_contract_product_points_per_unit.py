from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fidpha', '0008_add_ppv_to_product'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract_product',
            name='points_per_unit',
            field=models.DecimalField(
                max_digits=6,
                decimal_places=2,
                default=1,
                help_text='Points multiplier per dirham of PPV. Default 1 = 1 pt/MAD. e.g. 2.5 = 2.5 pts/MAD.',
            ),
        ),
    ]
