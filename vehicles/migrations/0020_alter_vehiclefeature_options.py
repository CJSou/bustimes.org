# Generated by Django 4.2 on 2023-04-14 17:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0019_remove_vehiclejourney_block"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="vehiclefeature",
            options={"ordering": ("name",)},
        ),
    ]
