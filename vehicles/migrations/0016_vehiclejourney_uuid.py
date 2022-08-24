# Generated by Django 4.0.7 on 2022-08-24 16:51

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0015_vehicle_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehiclejourney",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
