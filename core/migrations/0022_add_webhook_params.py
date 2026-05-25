# Generated migration for webhook_params field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_field_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='script',
            name='webhook_params',
            field=models.JSONField(blank=True, help_text='Parameter schema for auto-jobs UI. JSON array of param definitions.', null=True),
        ),
    ]
