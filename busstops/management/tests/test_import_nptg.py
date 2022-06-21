# coding=utf-8
import os
from django.test import TestCase
from .. import import_from_csv
from ..commands import (
    import_regions,
    import_areas,
    import_districts,
    import_localities,
    import_locality_hierarchy,
    import_adjacent_localities,
)
from ...models import Region, AdminArea, District, Locality, StopPoint


DIR = os.path.dirname(os.path.abspath(__file__))


class ImportNPTGTest(TestCase):
    """
    Test the import_regions, import_areas, import_districts and
    import_localities commands
    """

    @staticmethod
    def do_import(command, filename):
        filename = os.path.join(DIR, "fixtures/%s.csv" % filename)
        command.input = filename
        command.handle()

    @classmethod
    def setUpTestData(cls):
        cls.do_import(import_regions.Command(), "Regions")
        cls.do_import(import_areas.Command(), "AdminAreas")
        cls.do_import(import_districts.Command(), "Districts")
        cls.do_import(import_localities.Command(), "Localities")
        cls.do_import(import_locality_hierarchy.Command(), "LocalityHierarchy")
        cls.do_import(import_adjacent_localities.Command(), "AdjacentLocality")

        cls.east_anglia = Region.objects.get(id="EA")
        cls.east_midlands = Region.objects.get(id="EM")
        cls.london = Region.objects.get(id="L")

        cls.cambs = AdminArea.objects.get(pk=71)
        cls.derby = AdminArea.objects.get(pk=17)

        cls.district = District.objects.get(pk=29)

        cls.cambridge = Locality.objects.get(name="Cambridge")
        cls.addenbrookes = Locality.objects.get(name__startswith="Addenbrook")

    def test_regions(self):
        self.assertEqual(self.east_anglia.id, "EA")
        self.assertEqual(self.east_anglia.the(), "East Anglia")

        self.assertEqual(self.east_midlands.id, "EM")
        self.assertEqual(self.east_midlands.the(), "the East Midlands")

        self.assertEqual(self.london.id, "L")
        self.assertEqual(self.london.the(), "London")

    def test_areas(self):
        self.assertEqual(self.cambs.pk, 71)
        self.assertEqual(str(self.cambs), "Cambridgeshire")
        self.assertEqual(str(self.cambs.region), "East Anglia")

        self.assertEqual(self.derby.pk, 17)
        self.assertEqual(str(self.derby), "Derby")
        self.assertEqual(self.derby.region.the(), "the East Midlands")

    def test_districts(self):
        self.assertEqual(self.district.pk, 29)
        self.assertEqual(str(self.district), "Cambridge")
        self.assertEqual(str(self.district.admin_area), "Cambridgeshire")

    def test_localities(self):
        self.assertEqual(str(self.cambridge), "Cambridge")
        self.assertEqual(str(self.cambridge.district), "Cambridge")
        self.assertEqual(str(self.cambridge.district.admin_area), "Cambridgeshire")

        stop = StopPoint.objects.create(
            atco_code="1",
            common_name="Captain Birdseye Road",
            locality=self.addenbrookes,
            locality_centre=True,
            active=False,
        )

        # localities with no active stop points should return a 404
        self.assertEqual(
            404, self.client.get(self.cambridge.get_absolute_url()).status_code
        )
        self.assertEqual(
            404, self.client.get(self.addenbrookes.get_absolute_url()).status_code
        )
        self.assertEqual(404, self.client.get(stop.get_absolute_url()).status_code)

        stop.active = True
        stop.save()

        res = self.client.get(self.cambridge.get_absolute_url())
        self.assertContains(res, "Near Cambridge")
        self.assertContains(res, "Places in Cambridge")
        self.assertContains(res, "Addenbrooke")

    def test_super(self):
        command = import_from_csv.ImportFromCSVCommand()
        with self.assertRaises(NotImplementedError):
            command.handle_row(None)
