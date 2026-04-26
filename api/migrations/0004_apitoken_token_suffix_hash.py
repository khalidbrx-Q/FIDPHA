import hashlib
from django.db import migrations, models


def hash_existing_tokens(apps, schema_editor):
    """
    Hash all existing plain-text tokens and store the last 4 chars as suffix.
    Existing API clients keep working: sha256(old_raw) == new stored hash.
    """
    APIToken = apps.get_model('api', 'APIToken')
    for token in APIToken.objects.all():
        raw = token.token
        token.token_suffix = raw[-4:] if len(raw) >= 4 else raw
        token.token = hashlib.sha256(raw.encode()).hexdigest()
        token.save(update_fields=['token', 'token_suffix'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_apitokenusagelog'),
    ]

    operations = [
        migrations.AddField(
            model_name='apitoken',
            name='token_suffix',
            field=models.CharField(default='', editable=False, max_length=4),
        ),
        migrations.RunPython(hash_existing_tokens, migrations.RunPython.noop),
    ]
