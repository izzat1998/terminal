# Generated by Django 5.0.7 on 2024-09-30 16:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_alter_freedaycombination_category_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='freedaycombination',
            name='test_free_days',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
