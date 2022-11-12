from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from busstops.models import Operator, Region, Service

from .models import Licence


class VosaTest(TestCase):
    @override_settings(DATA_DIR=Path(__file__).resolve().parent / "fixtures")
    def test(self):
        with mock.patch(
            "vosa.management.commands.import_vosa.download_if_changed",
            return_value=(True, None),
        ):
            with self.assertNumQueries(6):
                call_command("import_vosa", "F")

        # multiple trading names
        licence = Licence.objects.get(licence_number="PF0000705")
        self.assertEqual(
            licence.trading_name,
            "R O SIMONDS\nSimonds Coach& Travel\nSimonds Countrylink",
        )

        Region.objects.create(id="SW", name="South West")
        operator = Operator.objects.create(
            region_id="SW", noc="AINS", name="Ainsley's Chariots"
        )
        service = Service.objects.create(current=True, line_name="33B")
        service.operator.add(operator)
        operator.licences.add(licence)

        response = self.client.get("/licences/PF0000705")
        self.assertContains(response, "Ainsley&#x27;s Chariots")
        self.assertContains(response, "<th>Trading name</th>")

        # licence
        response = self.client.get("/licences/PF1018256")
        self.assertEqual(1, len(response.context_data["registrations"]))
        self.assertEqual(2, len(response.context_data["cancelled"]))
        self.assertContains(response, "SANDERS COACHES LIMITED")
        self.assertContains(
            response, "LETHERINGSETT, GLANDFORD, WIVETON, CLEY, BLAKENEY"
        )

        # rss feed
        with self.assertNumQueries(2):
            response = self.client.get("/licences/PF1018256/rss")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SANDERS COACHES LIMITED")

        # licence 404
        with self.assertNumQueries(1):
            response = self.client.get("/licences/PH102095")
        self.assertEqual(response.status_code, 404)

        # registration
        with self.assertNumQueries(4):
            response = self.client.get("/registrations/PF1018256/2")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "WIVETON, CLEY, BLAKENEY, MORSTON, FIELD DALLING, HINDRINGHAM AND THURSFORD",
        )

        # registration 404
        with self.assertNumQueries(1):
            response = self.client.get("/registrations/PH1020951/d")
        self.assertEqual(response.status_code, 404)
