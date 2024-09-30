# Generated by Django 5.0.7 on 2024-09-26 06:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_terminalservice_container_size_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='terminalservicetype',
            name='unit_of_measure',
            field=models.CharField(choices=[('container', 'container'), ('day', 'day'), ('operation', 'operation'), ('unit', 'Unit')], max_length=50),
        ),
    ]