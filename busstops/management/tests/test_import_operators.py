import os
from unittest import skip
from django.test import TestCase
from ...models import Region, Operator, Service
from ..commands import import_operators

DIR = os.path.dirname(os.path.abspath(__file__))


class ImportOperatorsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        command = import_operators.Command()
        command.input = os.path.join(DIR, "fixtures", "NOC_DB.csv")

        cls.great_britain = Region.objects.create(id="GB", name="Great Britain")
        cls.scotland = Region.objects.create(id="S", name="Scotland")
        Region.objects.create(id="SW", name="South West")

        command.handle()

        cls.first_aberdeen = Operator.objects.get(id="FABD")
        cls.c2c = Operator.objects.get(id="CC")
        cls.ace_travel = Operator.objects.get(id="ACER")
        cls.weardale = Operator.objects.get(id="WRCT")
        cls.catch22bus = Operator.objects.get(id="NWOT")

        service = Service.objects.create(current=True, region=cls.scotland)
        service.operator.set(["BLUE", "NWOT"])

    @skip
    def test_operator_count(self):
        self.assertEqual(8, Operator.objects.count())

    def test_operator_id(self):
        """Is a strange NOC code (with an equals sign) correctly handled?"""
        self.assertEqual(self.c2c.id, "CC")
        self.assertEqual(self.c2c.name, "c2c")

    def test_operator_region(self):
        # Is the 'SC' region correctly identified as 'S' (Scotland)?
        self.assertEqual(self.first_aberdeen.region, self.scotland)

        # Is the 'Admin' region correctly identified as 'GB'?
        self.assertEqual(self.c2c.region, self.great_britain)

    def test_operator_name(self):
        """Is an uninformative OperatorPublicName like 'First' ignored in
        favour of the OperatorReferenceName?
        """
        self.assertEqual(self.first_aberdeen.name, "First in Aberdeen")
        self.assertEqual(self.c2c.name, "c2c")
        self.assertEqual(self.weardale.name, "Weardale Community Transport")
        self.assertEqual(self.catch22bus.name, "Catch22Bus Ltd")

        command = import_operators.Command()

        self.assertEqual(
            command.get_name(
                {
                    "OperatorPublicName": "Oakwood Travel",
                    "RefNm": "",
                    "OpNm": "Catch22Bus Ltd",
                }
            ),
            "Catch22Bus Ltd",
        )
        self.assertEqual(
            command.get_name(
                {"OperatorPublicName": "", "RefNm": "", "OpNm": "Loaches Coaches"}
            ),
            "Loaches Coaches",
        )

    def test_operator_mode(self):
        """Is an operator mode like 'DRT' expanded correctly to 'demand responsive transport'?"""
        self.assertEqual(self.ace_travel.vehicle_mode, "demand responsive transport")
        self.assertEqual(self.ace_travel.get_a_mode(), "A demand responsive transport")
        self.assertEqual(self.c2c.get_a_mode(), "A rail")
        self.assertEqual(self.first_aberdeen.get_a_mode(), "A bus")
        self.assertEqual(self.weardale.get_a_mode(), "A community transport")

    @skip
    def test_operator_ignore(self):
        """Were some rows correctly ignored?"""
        self.assertFalse(len(Operator.objects.filter(id="TVSR")))
