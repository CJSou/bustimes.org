import datetime
from pathlib import Path
from unittest.mock import patch

import time_machine
from django.core.management import call_command
from django.test import TestCase, override_settings

from busstops.models import DataSource, Operator, Region, Service, StopCode, StopPoint

from ...models import Route, Trip

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@override_settings(DATA_DIR=FIXTURES_DIR)
class FlixbusTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Region.objects.create(id="GB", name="Great Britain")

        Operator.objects.create(noc="FLIX", name="FlixBus")
        Operator.objects.create(noc="EMBR", name="Ember")

        sources = DataSource.objects.bulk_create(
            [
                DataSource(
                    name="Ember",
                ),
                DataSource(
                    name="FlixBus",
                ),
            ]
        )

        service = Service.objects.create(line_name="004")
        service.operator.add("FLIX")
        route = Route.objects.create(
            line_name="004", code="UK004", service=service, source=sources[1]
        )
        Trip.objects.create(
            route=route,
            operator_id="FLIX",
            start="00:00",
            end="00:00",
            vehicle_journey_code="UK004-10-1500032024-LVC#NOT-00",
        )
        Trip.objects.create(
            route=route,
            operator_id="FLIX",
            start="00:00",
            end="00:00",
            vehicle_journey_code="N401-1-1955102024-STB#VE-00",
        )

        StopPoint.objects.create(
            atco_code="6200247603", common_name="Aeropuerto d'Edinburgh", active=1
        )
        StopPoint.objects.create(
            atco_code="3390C11", common_name="Nottingham", active=1
        )
        StopCode.objects.create(
            source=sources[1],
            code="9b69e4fe-3ecb-11ea-8017-02437075395e",
            stop_id="3390C11",
        )

    def test_not_modified(self):
        with patch(
            "bustimes.management.commands.import_gtfs_flixbus.download_if_changed",
            return_value=(False, None),
        ):
            with self.assertNumQueries(2):
                call_command("import_gtfs_flixbus")

    @time_machine.travel("2023-01-01")
    def test_import_gtfs_flixbus(self):
        with patch(
            "bustimes.management.commands.import_gtfs_flixbus.download_if_changed",
            return_value=(
                True,
                datetime.datetime(2024, 6, 18, 10, 0, 0, tzinfo=datetime.timezone.utc),
            ),
        ):
            call_command("import_gtfs_flixbus")

        response = self.client.get("/operators/flixbus")
        self.assertContains(response, "London - Northampton - Nottingham")
        self.assertContains(response, "London - Cambridge")

        service = Service.objects.get(line_name="004")

        response = self.client.get(service.get_absolute_url())
        self.assertContains(
            response, "<td>10:30</td><td>15:00</td><td>19:15</td><td>23:40</td>"
        )
        self.assertContains(response, "/stops/3390C11")

        # British Summer Time:
        response = self.client.get(f"{service.get_absolute_url()}?date=2024-04-01")
        self.assertContains(
            response, "<td>10:30</td><td>15:00</td><td>19:15</td><td>23:40</td>"
        )

        self.assertEqual(Service.objects.all().count(), 2)

    @time_machine.travel("2023-01-01")
    def test_import_gtfs_ember(self):
        with patch(
            "bustimes.management.commands.import_gtfs_ember.download_if_changed",
            return_value=(
                True,
                datetime.datetime(2024, 6, 18, 10, 0, 0, tzinfo=datetime.timezone.utc),
            ),
        ):
            call_command("import_gtfs_ember")
            call_command("import_gtfs_ember")

        response = self.client.get("/operators/ember")

        service = Service.objects.get(line_name="E1")

        response = self.client.get(service.get_absolute_url())
        self.assertContains(response, "6200206520")
        self.assertContains(response, "/stops/6200247603")

        self.assertEqual(Service.objects.all().count(), 2)
