# Generated by Django 4.2 on 2023-04-14 17:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vosa", "0002_auto_20211002_2100"),
    ]

    operations = [
        migrations.AlterField(
            model_name="licence",
            name="licence_status",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
