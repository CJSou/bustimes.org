# Generated by Django 3.1.6 on 2021-02-04 16:28

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0010_auto_20210202_1951'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='vehiclelocation',
            name='datetime',
        ),
        migrations.RemoveIndex(
            model_name='vehiclelocation',
            name='datetime_latlong',
        ),
    ]
