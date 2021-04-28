"""Usage:

    ./manage.py import_stops < Stops.csv
"""

import re
from titlecase import titlecase
from django.contrib.gis.geos import Point
from ..import_from_csv import ImportFromCSVCommand
from ...models import Locality, StopPoint


INDICATORS_TO_PROPER_CASE = {indicator.lower(): indicator for indicator in (
    'opp',
    'adj',
    'at',
    'nr',
    'on',
    'o/s',
    'in',
    'behind',
    'before',
    'after',
    'N-bound',
    'NE-bound',
    'E-bound',
    'SE-bound',
    'S-bound',
    'SW-bound',
    'W-bound',
    'NW-bound',
)}

INDICATORS_TO_REPLACE = {
    'opp.': 'opp',
    'opposite': 'opp',
    'adjacent': 'adj',
    'near': 'nr',
    'before ': 'before',
    'outside': 'o/s',
    'os': 'o/s',
    'n bound': 'N-bound',
    'n - bound': 'N-bound',
    'ne bound': 'NE-bound',
    'ne - bound': 'NE-bound',
    'e bound': 'E-bound',
    'e - bound': 'E-bound',
    'se bound': 'SE-bound',
    'se - bound': 'SE-bound',
    's bound': 'S-bound',
    's - bound': 'S-bound',
    'sw bound': 'SW-bound',
    'sw - bound': 'SW-bound',
    'w bound': 'W-bound',
    'w - bound': 'W-bound',
    'nw bound': 'NW-bound',
    'nw - bound': 'NW-bound',
    'nb': 'N-bound',
    'eb': 'E-bound',
    'sb': 'S-bound',
    'wb': 'W-bound',
    'northbound': 'N-bound',
    'north bound': 'N-bound',
    'northeastbound': 'NE-bound',
    'north east bound': 'NE-bound',
    'eastbound': 'E-bound',
    'east-bound': 'E-bound',
    'east bound': 'E-bound',
    'south east bound': 'SE-bound',
    'southbound': 'S-bound',
    'south bound': 'S-bound',
    'south west bound': 'SW-bound',
    'wbound': 'W-bound',
    'westbound': 'W-bound',
    'west bound': 'W-bound',
    'nwbound': 'NW-bound',
    'northwestbound': 'NW-bound',
    'northwest bound': 'NW-bound',
    'north west bound': 'NW-bound',
}


def correct_case(value):
    if re.match(r'[A-Z]{3}', value) and any(char in 'AEIOU' for char in value):
        value = titlecase(value)
    return value


def to_camel_case(field_name):
    """
    Given a string like 'naptan_code', returns a string like 'NaptanCode'
    """
    return ''.join(s.title() for s in field_name.split('_'))


class Command(ImportFromCSVCommand):
    def handle_row(self, row):
        atco_code = row.get('ATCOCode') or row['AtcoCode']
        if atco_code in self.existing_stops:
            stop = self.existing_stops[atco_code]
            create = False
        else:
            stop = StopPoint(atco_code=atco_code)
            create = True

        stop.locality_centre = (row['LocalityCentre'] == '1')
        stop.active = (row.get('Status', 'act') == 'act')
        stop.admin_area_id = row.get('AdministrativeAreaCode') or row['AdministrativeAreaRef']

        if row['Longitude'] and float(row['Longitude']) != 0:
            stop.latlong = Point(
                float(row['Longitude']),
                float(row['Latitude']),
                srid=4326  # World Geodetic System
            )
        elif row['Easting']:
            stop.latlong = Point(int(row['Easting']), int(row['Northing']), srid=27700)

        if 'NptgLocalityCode' in row:
            stop.locality_id = row['NptgLocalityCode']
        elif row['NptgLocalityRef']:
            # Ireland
            stop.locality_id = row['NptgLocalityRef']
            if not Locality.objects.filter(pk=stop.locality_id).exists():
                Locality.objects.create(pk=stop.locality_id, admin_area_id=stop.admin_area_id)

        for django_field_name, naptan_field_name in self.field_names:
            if naptan_field_name not in row:
                naptan_field_name += '_lang_en'
            if naptan_field_name not in row:
                continue
            value = row[naptan_field_name].strip()
            if django_field_name in ('street', 'crossing', 'landmark', 'indicator', 'common_name'):
                if value.lower() in ('-', '--', '---', '*', 'tba', 'unknown', 'n/a',
                                     'data unavailable'):
                    value = ''
                elif django_field_name != 'indicator' and value.isupper():
                    value = correct_case(value)
            value = value.replace('`', '\'')  # replace backticks
            setattr(stop, django_field_name, value)

        lower_indicator = stop.indicator.lower()
        if lower_indicator in INDICATORS_TO_REPLACE:
            stop.indicator = INDICATORS_TO_REPLACE[lower_indicator]
        elif lower_indicator.lower() in INDICATORS_TO_PROPER_CASE:
            stop.indicator = INDICATORS_TO_PROPER_CASE[lower_indicator]
        elif stop.indicator.startswith('220'):
            stop.indicator = ''

        if stop.stop_type == 'class_undefined':
            stop.stop_type = ''
        if stop.bus_stop_type == 'type_undefined':
            stop.bus_stop_type = ''

        if 'CompassPoint' in row:
            stop.bearing = row['CompassPoint']

        return stop, create

    def handle_rows(self, rows):
        rows = list(rows)

        django_field_names = [
            'naptan_code',
            'common_name',
            'landmark',
            'street',
            'crossing',
            'indicator',
            'suburb',
            'stop_type',
            'bus_stop_type',
            'timing_status',
            'town',
            'bearing',
        ]
        # A list of tuples like ('naptan_code', 'NaptanCode')
        self.field_names = [(name, to_camel_case(name)) for name in django_field_names]

        stop_codes = [row.get('ATCOCode') or row['AtcoCode'] for row in rows]
        self.existing_stops = StopPoint.objects.in_bulk(stop_codes)
        to_update = []
        to_create = []

        for row in rows:
            stop, create = self.handle_row(row)
            if create:
                to_create.append(stop)
            else:
                to_update.append(stop)

        StopPoint.objects.bulk_create(to_create)
        StopPoint.objects.bulk_update(to_update, fields=[
            'locality_centre', 'active', 'admin_area', 'latlong', 'locality'
        ] + django_field_names)
