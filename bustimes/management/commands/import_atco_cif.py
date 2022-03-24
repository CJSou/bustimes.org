import os
import zipfile
from datetime import date, timedelta, datetime
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.utils import timezone
from busstops.models import Service, DataSource, StopPoint
from ...models import Route, Calendar, CalendarDate, Trip, StopTime, Note


def parse_date(string):
    if string == b'99999999':
        return
    try:
        return date(year=int(string[:4]), month=int(string[4:6]), day=int(string[6:]))
    except ValueError:
        print(string)


def parse_time(string):
    return timedelta(hours=int(string[:2]), minutes=int(string[2:]))


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('filenames', nargs='+', type=str)

    def handle(self, *args, **options):
        for archive_name in options['filenames']:

            if 'ulb' in archive_name.lower() or 'ulsterbus' in archive_name.lower():
                source_name = 'ULB'
            else:
                source_name = 'MET'
            self.source, _ = DataSource.objects.get_or_create(name=source_name)

            self.source.datetime = datetime.fromtimestamp(os.path.getmtime(archive_name), timezone.utc)

            self.handle_archive(archive_name)

    def handle_archive(self, archive_name):
        self.routes = {}
        self.calendars = {}

        with zipfile.ZipFile(archive_name) as archive:
            for filename in archive.namelist():
                if filename.endswith('.cif'):
                    with archive.open(filename) as open_file:
                        self.handle_file(open_file)
        assert self.stop_times == []

        services = {route.service.id: route.service for route in self.routes.values()}.values()

        for service in services:
            service.do_stop_usages()

            service.update_geometry(save=False)

        Service.objects.bulk_update(services,
                                    fields=['geometry', 'description', 'outbound_description', 'inbound_description'])
        for service in services:
            service.update_search_vector()

        self.source.route_set.exclude(code__in=self.routes.keys()).delete()
        self.source.service_set.filter(current=True).exclude(service_code__in=self.routes.keys()).update(current=False)
        self.source.save(update_fields=['datetime'])

    def handle_file(self, open_file):
        self.route = None
        self.trip = None
        self.stop_times = []
        self.notes = []

        encoding = 'cp1252'

        # stops
        stops = {}
        for line in open_file:
            identity = line[:2]
            if identity == b'QL' or identity == b'QB':
                stop_code = line[3:15].decode().strip()
                if identity == b'QL':
                    name = line[15:63]
                    if name and stop_code not in stops:
                        name = name.decode(encoding).strip()
                        stops[stop_code] = StopPoint(atco_code=stop_code, common_name=name, active=True)
                elif stop_code in stops:
                    easting = line[15:23].strip()
                    northing = line[23:31].strip()
                    if easting:
                        stops[stop_code].latlong = Point(
                            int(easting),
                            int(northing),
                            srid=29902  # Irish Grid
                        )
        existing_stops = StopPoint.objects.in_bulk(stops.keys())
        stops_to_update = []
        new_stops = []
        for stop_code in stops:
            if stop_code in existing_stops:
                stops_to_update.append(stops[stop_code])
            else:
                new_stops.append(stops[stop_code])
        StopPoint.objects.bulk_update(stops_to_update, fields=['common_name', 'latlong'])
        StopPoint.objects.bulk_create(new_stops)

        open_file.seek(0)

        # everything else
        previous_line = None
        for line in open_file:
            self.handle_line(line, previous_line, encoding)
            previous_line = line

    def get_calendar(self):
        line = self.trip_header
        key = line[13:38].decode() + str(self.exceptions)
        if key in self.calendars:
            return self.calendars[key]
        calendar = Calendar.objects.create(
            mon=line[29:30] == b'1',
            tue=line[30:31] == b'1',
            wed=line[31:32] == b'1',
            thu=line[32:33] == b'1',
            fri=line[33:34] == b'1',
            sat=line[34:35] == b'1',
            sun=line[35:36] == b'1',
            start_date=parse_date(line[13:21]),
            end_date=parse_date(line[21:29])
        )
        CalendarDate.objects.bulk_create(
            CalendarDate(
                calendar=calendar,
                start_date=parse_date(exception[2:10]),
                end_date=parse_date(exception[10:18]),
                operation=exception[18:19] == b'1',
            ) for exception in self.exceptions
        )

        self.calendars[key] = calendar
        return calendar

    def handle_line(self, line, previous_line, encoding):
        identity = line[:2]

        if identity == b'QD':
            operator = line[3:7].decode().strip()
            line_name = line[7:11].decode().strip()
            key = f'{line_name}_{operator}'.upper()
            direction = line[11:12]
            description = line[12:].decode().strip()
            if key in self.routes:
                self.route = self.routes[key]
                if direction == b'O':
                    self.routes[key].service.description = description
                    self.routes[key].service.outbound_description = description
                else:
                    self.routes[key].service.inbound_description = description
            else:
                defaults = {
                    'line_name': line_name,
                    'description': description,
                    'date': self.source.datetime.date(),
                    'current': True,
                    'source': self.source,
                    'region_id': 'NI'
                }
                if direction == b'O':
                    defaults['description'] = description
                    defaults['outbound_description'] = description
                else:
                    defaults['inbound_description'] = description
                service, _ = Service.objects.update_or_create(defaults, service_code=key)
                if operator:
                    service.operator.add(operator)
                self.route, created = Route.objects.update_or_create(
                    {
                        'service': service,
                        'line_name': line_name,
                        'description': description,
                    }, code=key, source=self.source
                )
                if not created:
                    self.route.trip_set.all().delete()
                self.routes[key] = self.route

        elif identity == b'QS':
            self.sequence = 0
            self.trip_header = line
            self.exceptions = []

        elif identity == b'QE':
            self.exceptions.append(line)

        elif identity == b'QO':  # origin stop
            if self.route:
                calendar = self.get_calendar()
                self.trip = Trip(
                    route=self.route,
                    calendar=calendar,
                    inbound=self.trip_header[64:65] == b'I'
                )

                departure = parse_time(line[14:18])
                self.stop_times.append(
                    StopTime(
                        arrival=departure,
                        departure=departure,
                        stop_id=line[2:14].decode().strip(),
                        sequence=0,
                        trip=self.trip
                    )
                )
                self.trip.start = departure

        elif identity == b'QI':  # intermediate stop
            if self.trip:
                self.sequence += 1
                timing_status = line[26:28]
                if timing_status == b'T1':
                    timing_status = 'PTP'
                elif timing_status == b'T0':
                    timing_status = 'OTH'
                else:
                    print(line)
                    return
                self.stop_times.append(
                    StopTime(
                        arrival=parse_time(line[14:18]),
                        departure=parse_time(line[18:22]),
                        stop_id=line[2:14].decode().strip(),
                        sequence=self.sequence,
                        trip=self.trip,
                        timing_status=timing_status
                    )
                )

        elif identity == b'QT':  # destination stop
            if self.trip:
                arrival = parse_time(line[14:18])
                self.sequence += 1
                stop_code = line[2:14].decode().strip()
                self.stop_times.append(
                    StopTime(
                        arrival=arrival,
                        departure=arrival,
                        stop_id=stop_code,
                        sequence=self.sequence,
                        trip=self.trip
                    )
                )
                self.trip.destination_id = stop_code
                self.trip.end = arrival

                self.trip.save()

                self.trip.notes.set(self.notes)
                self.notes = []

                for stop_time in self.stop_times:
                    stop_time.trip = stop_time.trip  # set trip_id
                StopTime.objects.bulk_create(self.stop_times)
                self.stop_times = []

        elif identity == b'QN':  # note
            previous_identity = previous_line[:2]
            note = line[7:].decode(encoding).strip()
            if previous_identity == b'QO' or previous_identity == b'QI' or previous_identity == b'QT':
                note = note.lower()
                if note == 'pick up only' or note == 'pick up  only':
                    if previous_identity != b'QT':
                        self.stop_times[-1].set_down = False
                elif note == 'set down only' or note == '.set down only' or note == 'drop off only':
                    if previous_identity != b'QT':
                        self.stop_times[-1].pick_up = False
                else:
                    print(note)
            elif previous_identity == b'QS' or previous_identity == b'QE' or previous_identity == b'QN':
                code = line[2:7].decode(encoding).strip()
                note, _ = Note.objects.get_or_create(code=code, text=note)
                self.notes.append(note)
            else:
                print(previous_identity[:2], line)
