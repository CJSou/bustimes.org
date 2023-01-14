from pathlib import Path

import vcr
from django.core.management import call_command
from django.test import TestCase

from ...models import Operator, Region


class ImportOperatorsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Region.objects.create(id="GB", name="Great Britain")
        Region.objects.create(id="S", name="Scotland")
        Region.objects.create(id="W", name="Wales")
        Region.objects.create(id="WM", name="West Midlands")
        Region.objects.create(id="SW", name="South West")
        Region.objects.create(id="SE", name="South East")
        Region.objects.create(id="EM", name="East Midlands")
        Region.objects.create(id="NE", name="North East")
        Region.objects.create(id="NW", name="North West")
        Region.objects.create(id="EA", name="East Anglia")
        Region.objects.create(id="Y", name="Yorkshire")
        Region.objects.create(id="L", name="London")

        # Operator.objects.create(noc="A1CS", name="A1 Coaches")
        # Operator.objects.create(noc="AMSY", name="Arriva North West")
        # Operator.objects.create(noc="ANWE", name="Arriva North West")
        # Operator.objects.create(noc="AMAN", name="Arriva North West")
        # Operator.objects.create(noc="AMID", name="Arriva Midlands")
        # Operator.objects.create(noc="AFCL", name="Arriva Midlands")

    def test_import_noc(self):

        FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

        with vcr.use_cassette(
            str(FIXTURES_DIR / "noc.yaml"),
            decode_compressed_response=True,
        ):
            with self.assertNumQueries(3982):
                call_command("import_noc")

        c2c = Operator.objects.get(noc="CC")
        self.assertEqual(c2c.name, "c2c")
        self.assertEqual(c2c.region_id, "GB")
        self.assertEqual(c2c.vehicle_mode, "rail")

        aact = Operator.objects.get(noc="AACT")
        self.assertEqual(aact.region_id, "Y")
        self.assertEqual(aact.vehicle_mode, "bus")

        actr = Operator.objects.get(noc="ACTR")
        self.assertEqual(actr.vehicle_mode, "demand responsive transport")

        wray = Operator.objects.get(noc="WRAY")
        self.assertEqual(wray.url, "https://www.arrivabus.co.uk/yorkshire")
        self.assertEqual(wray.twitter, "arrivayorkshire")

        kernow = Operator.objects.get(noc="FCWL")
        self.assertEqual(kernow.url, "https://www.firstbus.co.uk/cornwall")
        self.assertEqual(kernow.twitter, "by_Kernow")

        cymru = Operator.objects.get(noc="FCYM")
        self.assertEqual(cymru.name, "First Cymru")

        notb = Operator.objects.get(noc="NOTB")
        self.assertEqual(notb.url, "")
