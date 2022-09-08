import os
from unittest.mock import patch

import time_machine
import vcr
from django.test import TestCase
from django.utils import timezone

from busstops.models import DataSource, Operator, Region, Service

from ...models import VehicleJourney
from ..commands.import_stagecoach import Command


class MockException(Exception):
    pass


DIR = os.path.dirname(os.path.abspath(__file__))


@time_machine.travel("2019-11-17T04:32:00.000Z")
class StagecoachTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = DataSource.objects.create(
            name="Stagecoach", datetime=timezone.now()
        )

        r = Region.objects.create(pk="SE")
        o = Operator.objects.create(
            pk="SCOX", name="Oxford", parent="Stagecoach", vehicle_mode="bus", region=r
        )
        s = Service.objects.create(
            line_name="Oxford Tube",
            geometry="MULTILINESTRING((-0.1475818977 51.4928233539,-0.1460401487 51.496737716))",
        )
        s.operator.add(o)

    @patch("vehicles.management.import_live_vehicles.sleep")
    @patch(
        "vehicles.management.commands.import_stagecoach.sleep",
        side_effect=MockException,
    )
    def test_handle(self, sleep_1, sleep_2):
        command = Command()
        command.source = self.source
        command.operator_codes = ["SDVN"]

        with vcr.use_cassette(os.path.join(DIR, "vcr", "stagecoach_vehicles.yaml")):
            with self.assertLogs(level="ERROR"):
                with self.assertNumQueries(18):
                    with patch("builtins.print"):
                        with self.assertRaises(MockException):
                            command.handle()

        self.assertTrue(sleep_1.called)
        self.assertTrue(sleep_2.called)
        self.assertEqual(
            command.operators,
            {
                "SCOX": Operator(noc="SCOX"),
                "SCCM": None,
                "SCEK": None,
            },
        )
        self.assertEqual(VehicleJourney.objects.count(), 1)
