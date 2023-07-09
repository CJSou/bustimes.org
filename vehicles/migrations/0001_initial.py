# Generated by Django 4.2.3 on 2023-07-09 13:39

import autoslug.fields
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.datetime
import django.db.models.functions.text
import simple_history.models
import uuid
import vehicles.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('bustimes', '0001_initial'),
        ('busstops', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Livery',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('colour', models.CharField(help_text='For the most simplified version of the livery', max_length=7)),
                ('colours', models.CharField(blank=True, help_text="Keep it simple.\nSimplicity (and being able to read the route number on the map) is much more important than 'accuracy'.", max_length=512)),
                ('css', models.CharField(blank=True, help_text='Leave this blank.\nA livery can be adequately represented with a list of colours and an angle.', max_length=1024, verbose_name='CSS')),
                ('left_css', models.CharField(blank=True, help_text='Automatically generated from colours and angle', max_length=1024, verbose_name='Left CSS')),
                ('right_css', models.CharField(blank=True, help_text='Automatically generated from colours and angle', max_length=1024, verbose_name='Right CSS')),
                ('white_text', models.BooleanField(default=False)),
                ('text_colour', models.CharField(blank=True, max_length=7)),
                ('stroke_colour', models.CharField(blank=True, help_text='Use sparingly, often looks shit', max_length=7)),
                ('horizontal', models.BooleanField(default=False, help_text='Equivalent to setting the angle to 90')),
                ('angle', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('locked', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
                ('published', models.BooleanField(help_text='Tick to include in the CSS and be able to apply this livery to vehicles')),
                ('operators', models.ManyToManyField(blank=True, related_name='liveries', to='busstops.operator')),
            ],
            options={
                'verbose_name_plural': 'liveries',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', autoslug.fields.AutoSlugField(editable=True, populate_from=vehicles.models.vehicle_slug, unique=True)),
                ('code', models.CharField(max_length=255)),
                ('fleet_number', models.PositiveIntegerField(blank=True, null=True)),
                ('fleet_code', models.CharField(blank=True, max_length=24)),
                ('reg', models.CharField(blank=True, max_length=24)),
                ('colours', models.CharField(blank=True, max_length=255)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('branding', models.CharField(blank=True, max_length=255)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('latest_journey_data', models.JSONField(blank=True, null=True)),
                ('withdrawn', models.BooleanField(default=False)),
                ('data', models.JSONField(blank=True, null=True)),
                ('locked', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='VehicleEdit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fleet_number', models.CharField(blank=True, max_length=24)),
                ('reg', models.CharField(blank=True, max_length=24)),
                ('vehicle_type', models.CharField(blank=True, max_length=255)),
                ('colours', models.CharField(blank=True, max_length=255)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('branding', models.CharField(blank=True, max_length=255)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('withdrawn', models.BooleanField(null=True)),
                ('changes', models.JSONField(blank=True, null=True)),
                ('url', models.URLField(blank=True, max_length=255)),
                ('approved', models.BooleanField(db_index=True, null=True)),
                ('score', models.SmallIntegerField(default=0)),
                ('datetime', models.DateTimeField(blank=True, null=True)),
                ('arbiter', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='arbited', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='VehicleFeature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='VehicleRevision',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datetime', models.DateTimeField()),
                ('changes', models.JSONField(blank=True, null=True)),
                ('message', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='VehicleType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('style', models.CharField(blank=True, choices=[('double decker', 'double decker'), ('minibus', 'minibus'), ('coach', 'coach'), ('articulated', 'articulated'), ('train', 'train'), ('tram', 'tram')], max_length=13)),
                ('fuel', models.CharField(blank=True, choices=[('diesel', 'diesel'), ('electric', 'electric'), ('hybrid', 'hybrid'), ('hydrogen', 'hydrogen'), ('gas', 'gas')], max_length=8)),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='VehicleRevisionFeature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('add', models.BooleanField(default=True)),
                ('feature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehiclefeature')),
                ('revision', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehiclerevision')),
            ],
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='features',
            field=models.ManyToManyField(blank=True, through='vehicles.VehicleRevisionFeature', to='vehicles.vehiclefeature'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='from_livery',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revision_from', to='vehicles.livery'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='from_operator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revision_from', to='busstops.operator'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='from_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revision_from', to='vehicles.vehicletype'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='to_livery',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revision_to', to='vehicles.livery'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='to_operator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revision_to', to='busstops.operator'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='to_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revision_to', to='vehicles.vehicletype'),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='vehiclerevision',
            name='vehicle',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicle'),
        ),
        migrations.CreateModel(
            name='VehicleJourney',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datetime', models.DateTimeField()),
                ('route_name', models.CharField(blank=True, max_length=64)),
                ('code', models.CharField(blank=True, max_length=255)),
                ('destination', models.CharField(blank=True, max_length=255)),
                ('direction', models.CharField(blank=True, max_length=8)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('service', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='busstops.service')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='busstops.datasource')),
                ('trip', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='bustimes.trip')),
                ('vehicle', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicle')),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.CreateModel(
            name='VehicleEditVote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('positive', models.BooleanField()),
                ('by_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('for_edit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicleedit')),
                ('for_revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehiclerevision')),
            ],
        ),
        migrations.CreateModel(
            name='VehicleEditFeature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('add', models.BooleanField(default=True)),
                ('edit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicleedit')),
                ('feature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehiclefeature')),
            ],
        ),
        migrations.AddField(
            model_name='vehicleedit',
            name='features',
            field=models.ManyToManyField(blank=True, through='vehicles.VehicleEditFeature', to='vehicles.vehiclefeature'),
        ),
        migrations.AddField(
            model_name='vehicleedit',
            name='livery',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='vehicles.livery'),
        ),
        migrations.AddField(
            model_name='vehicleedit',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='vehicleedit',
            name='vehicle',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicle'),
        ),
        migrations.CreateModel(
            name='VehicleCode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100)),
                ('scheme', models.CharField(max_length=24)),
                ('vehicle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vehicles.vehicle')),
            ],
        ),
        migrations.AddField(
            model_name='vehicle',
            name='features',
            field=models.ManyToManyField(blank=True, to='vehicles.vehiclefeature'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='garage',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='bustimes.garage'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='latest_journey',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='latest_vehicle', to='vehicles.vehiclejourney'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='livery',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='vehicles.livery'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='operator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='busstops.operator'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='source',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='busstops.datasource'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='vehicle_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='vehicles.vehicletype'),
        ),
        migrations.CreateModel(
            name='HistoricalLivery',
            fields=[
                ('id', models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('colour', models.CharField(help_text='For the most simplified version of the livery', max_length=7)),
                ('colours', models.CharField(blank=True, help_text="Keep it simple.\nSimplicity (and being able to read the route number on the map) is much more important than 'accuracy'.", max_length=512)),
                ('css', models.CharField(blank=True, help_text='Leave this blank.\nA livery can be adequately represented with a list of colours and an angle.', max_length=1024, verbose_name='CSS')),
                ('left_css', models.CharField(blank=True, help_text='Automatically generated from colours and angle', max_length=1024, verbose_name='Left CSS')),
                ('right_css', models.CharField(blank=True, help_text='Automatically generated from colours and angle', max_length=1024, verbose_name='Right CSS')),
                ('white_text', models.BooleanField(default=False)),
                ('text_colour', models.CharField(blank=True, max_length=7)),
                ('stroke_colour', models.CharField(blank=True, help_text='Use sparingly, often looks shit', max_length=7)),
                ('horizontal', models.BooleanField(default=False, help_text='Equivalent to setting the angle to 90')),
                ('angle', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('locked', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
                ('published', models.BooleanField(help_text='Tick to include in the CSS and be able to apply this livery to vehicles')),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical livery',
                'verbose_name_plural': 'historical liveries',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AddIndex(
            model_name='vehiclejourney',
            index=models.Index(models.F('service'), models.OrderBy(django.db.models.functions.datetime.TruncDate('datetime')), name='service_datetime_date'),
        ),
        migrations.AddIndex(
            model_name='vehiclejourney',
            index=models.Index(models.F('vehicle'), models.OrderBy(django.db.models.functions.datetime.TruncDate('datetime')), name='vehicle_datetime_date'),
        ),
        migrations.AlterUniqueTogether(
            name='vehiclejourney',
            unique_together={('vehicle', 'datetime')},
        ),
        migrations.AlterUniqueTogether(
            name='vehicleeditvote',
            unique_together={('by_user', 'for_edit')},
        ),
        migrations.AlterIndexTogether(
            name='vehiclecode',
            index_together={('code', 'scheme')},
        ),
        migrations.AddIndex(
            model_name='vehicle',
            index=models.Index(django.db.models.functions.text.Upper('fleet_code'), name='fleet_code'),
        ),
        migrations.AddIndex(
            model_name='vehicle',
            index=models.Index(django.db.models.functions.text.Upper('reg'), name='reg'),
        ),
        migrations.AddIndex(
            model_name='vehicle',
            index=models.Index(fields=['operator', 'withdrawn'], name='operator_withdrawn'),
        ),
        migrations.AddConstraint(
            model_name='vehicle',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Upper('code'), models.F('operator'), name='vehicle_operator_and_code'),
        ),
    ]
