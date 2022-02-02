"""
Usage:

    ./manage.py import_transxchange EA.zip [EM.zip etc]
"""

import logging
import os
import re
import csv
import zipfile
import datetime
from functools import cache
from titlecase import titlecase
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Upper
from django.utils import timezone
from busstops.models import Operator, Service, DataSource, StopPoint, StopUsage, ServiceCode, ServiceLink
from ...models import (Route, Trip, StopTime, Note, Garage, VehicleType, Block, RouteLink,
                       Calendar, CalendarDate, CalendarBankHoliday, BankHoliday)
from transxchange.txc import TransXChange
from vosa.models import Registration


logger = logging.getLogger(__name__)

"""
_________________________________________________________________________________________________
| AllBankHolidays | AllHolidaysExceptChristmas | Holidays             | NewYearsDay              |
|                 |                            |                      | 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Jan2ndScotland        |
|                 |                            |                      | GoodFriday               |
|                 |                            |                      | 🏴󠁧󠁢󠁳󠁣󠁴󠁿 StAndrewsDay          |
|                 |                            |______________________|__________________________|
|                 |                            | HolidayMondays       | EasterMonday             |
|                 |                            |                      | MayDay                   |
|                 |                            |                      | SpringBank               |________
|                 |                            |                      | LateSummerBankHolidayNotScotland  |
|                 |                            |                      | AugustBankHolidayScotland   ______|
|                 |____________________________|______________________|____________________________|
|                 | Christmas            | ChristmasDay               |
|                 |                      | BoxingDay                  |
|                 |______________________|____________________________|
|                 | DisplacementHolidays | ChristmasDayHoliday        |
|                 |                      | BoxingDayHoliday           |
|                 |                      | NewYearsDayHoliday         |
|                 |                      | 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Jan2ndScotlandHoliday   |
|                 |                      | 🏴󠁧󠁢󠁳󠁣󠁴󠁿 StAndrewsDayHoliday     |
|_________________|______________________|____________________________|
| EarlyRunOff     | ChristmasEve |
|                 | NewYearsEve  |
|_________________|______________|
"""

BODS_SERVICE_CODE_REGEX = re.compile(r'^P[BCDFGHKM]\d+:\d+.*$')


def initialisms(word, **kwargs):
    if word in ('YMCA', 'PH'):
        return word


def get_summary(summary):
    # London wtf
    if summary == 'not School vacation in free public holidays regulation holidays':
        return 'not school holidays'

    summary = summary.replace(' days days', ' days')
    summary = summary.replace('olidays holidays', 'olidays')
    summary = summary.replace('AnySchool', 'school')

    summary = re.sub(r'(?i)(school(day)?s)', 'school', summary)

    return summary


def get_service_code(filename):
    """
    Given a filename like 'ea_21-45A-_-y08-1.xml',
    returns a service_code like 'ea_21-45A-_-y08'
    """
    parts = filename.split('-')  # ['ea_21', '3', '_', '1']
    if len(parts) == 5:
        net = parts[0].split('_')[0]
        if len(net) <= 3 and net.isalpha() and net.islower():
            return '-'.join(parts[:-1])


def get_operator_name(operator_element):
    "Given an Operator element, returns the operator name or None"

    for element_name in ('TradingName', 'OperatorNameOnLicence', 'OperatorShortName'):
        name = operator_element.findtext(element_name)
        if name:
            return name.replace('&amp;', '&')


@cache
def get_operator_by(scheme, code):
    if code:
        try:
            return Operator.objects.filter(operatorcode__code=code, operatorcode__source__name=scheme).distinct().get()
        except (Operator.DoesNotExist, Operator.MultipleObjectsReturned):
            pass


def get_open_data_operators():
    open_data_operators = []
    incomplete_operators = []
    for operator_code, _, operators, incomplete in settings.BOD_OPERATORS:
        if operators:
            operators = operators.values()
        else:
            operators = [operator_code]
        if incomplete:
            incomplete_operators += operators
        open_data_operators += operators
    for _, _, _, operators in settings.PASSENGER_OPERATORS:
        open_data_operators += operators.values()
    for _, _, _, operators in settings.STAGECOACH_OPERATORS:
        open_data_operators += operators
    for setting in settings.TICKETER_OPERATORS:
        open_data_operators += setting[1]

    open_data_operators = set(open_data_operators)
    incomplete_operators = set(incomplete_operators)
    open_data_operators -= incomplete_operators
    return open_data_operators, incomplete_operators


def get_calendar_date(date, operation, summary):
    return CalendarDate(
        start_date=date,
        end_date=date,
        special=operation,
        operation=operation,
        summary=summary
    )


def get_registration(service_code):
    parts = service_code.split('_')[0].split(':')
    if len(parts[0]) != 9:
        prefix = parts[0][:2]
        suffix = str(int(parts[0][2:]))
        parts[0] = f'{prefix}{suffix.zfill(7)}'
    if parts[1] and parts[1].isdigit():
        try:
            return Registration.objects.get(
                registration_number=f'{parts[0]}/{int(parts[1])}'
            )
        except Registration.DoesNotExist:
            pass


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('archives', nargs=1, type=str)
        parser.add_argument('files', nargs='*', type=str)

    def set_up(self):
        self.service_descriptions = {}
        self.calendar_cache = {}
        self.operators = {}
        self.missing_operators = []
        self.notes = {}
        self.garages = {}

    def handle(self, *args, **options):
        self.set_up()

        self.open_data_operators, self.incomplete_operators = get_open_data_operators()

        for archive_name in options['archives']:
            self.handle_archive(archive_name, options['files'])

        self.debrief()

    def debrief(self):
        """
        Log the names of any undefined public holiday names, and operators that couldn't be found
        """
        for operator in self.missing_operators:
            logger.warning(str(operator))

    def set_region(self, archive_name):
        """
        Set region_id and source based on the name of the TNDS archive, creating a DataSource if necessary
        """
        archive_name = os.path.basename(archive_name)  # ea.zip
        region_id, _ = os.path.splitext(archive_name)  # ea
        self.region_id = region_id.upper()  # EA

        if len(self.region_id) > 2:
            if self.region_id == 'NCSD':
                self.region_id = 'GB'
            elif self.region_id == 'IOM':
                self.region_id = 'IM'
            else:
                self.region_id = None

        if self.region_id:
            self.source, _ = DataSource.objects.get_or_create(
                {
                    'url': 'ftp://ftp.tnds.basemap.co.uk/' + archive_name
                },
                name=self.region_id
            )
        else:
            self.source, _ = DataSource.objects.get_or_create(name=archive_name)

    def get_operator(self, operator_element):
        """
        Given an Operator element, returns an operator code for an operator that exists
        """

        operator_code = operator_element.findtext('NationalOperatorCode')
        if not self.is_tnds():
            if not operator_code:
                operator_code = operator_element.findtext('OperatorCode')
            operator_code = self.operators.get(operator_code, operator_code)

        operator = get_operator_by('National Operator Codes', operator_code)
        if operator:
            return operator

        licence_number = operator_element.findtext('LicenceNumber')
        if licence_number:
            try:
                return Operator.objects.get(licences__licence_number=licence_number)
            except (Operator.DoesNotExist, Operator.MultipleObjectsReturned):
                pass

        name = get_operator_name(operator_element)

        try:
            return Operator.objects.get(name=name)
        except (Operator.DoesNotExist, Operator.MultipleObjectsReturned):
            pass

        # Get by regional operator code
        operator_code = operator_element.findtext('OperatorCode')
        if operator_code:
            operator = get_operator_by(self.region_id, operator_code)
            if not operator:
                operator = get_operator_by('National Operator Codes', operator_code)
            if operator:
                return operator

        missing_operator = {
            element.tag: element.text.strip() for element in operator_element if element.text
        }
        if missing_operator not in self.missing_operators:
            self.missing_operators.append(missing_operator)

    def get_operators(self, transxchange, service):
        operators = transxchange.operators
        if len(operators) > 1:
            journey_operators = {
                journey.operator for journey in transxchange.journeys
                if journey.operator and journey.service_ref == service.service_code
            }
            journey_operators.add(service.operator)
            operators = [operator for operator in operators if operator.get('id') in journey_operators]
        operators = (self.get_operator(operator) for operator in operators)
        return [operator for operator in operators if operator]

    def set_service_descriptions(self, archive):
        """
        If there's a file named 'IncludedServices.csv', as there is in 'NCSD.zip', use it
        """
        if 'IncludedServices.csv' in archive.namelist():
            with archive.open('IncludedServices.csv') as csv_file:
                reader = csv.DictReader(line.decode('utf-8') for line in csv_file)
                # e.g. {'NATX323': 'Cardiff - Liverpool'}
                for row in reader:
                    key = f"{row['Operator']}{row['LineName']}{row['Dir']}"
                    self.service_descriptions[key] = row['Description']

    def get_service_descriptions(self, filename):
        parts = filename.split('_')
        operator = parts[-2]
        line_name = parts[-1][:-4]
        key = f'{operator}{line_name}'
        outbound = self.service_descriptions.get(f'{key}O', '')
        inbound = self.service_descriptions.get(f'{key}I', '')
        return outbound, inbound

    def mark_old_services_as_not_current(self):
        self.source.route_set.exclude(id__in=self.route_ids).delete()
        old_services = self.source.service_set.filter(current=True, route=None).exclude(id__in=self.service_ids)
        old_services.update(current=False)

    def handle_archive(self, archive_name, filenames):
        self.service_ids = set()
        self.route_ids = set()

        self.set_region(archive_name)

        self.source.datetime = datetime.datetime.fromtimestamp(os.path.getmtime(archive_name), timezone.utc)

        try:
            with zipfile.ZipFile(archive_name) as archive:

                self.set_service_descriptions(archive)

                namelist = archive.namelist()

                if 'NCSD_TXC_2_4/' in namelist:
                    filenames = [filename for filename in namelist if filename.startswith('NCSD_TXC_2_4/')]

                for filename in filenames or namelist:
                    if filename.endswith('.xml'):
                        with archive.open(filename) as open_file:
                            self.handle_file(open_file, filename)
        except zipfile.BadZipfile:
            with open(archive_name) as open_file:
                self.handle_file(open_file, archive_name)

        if not filenames:
            self.mark_old_services_as_not_current()
            self.source.service_set.filter(current=False, geometry__isnull=False).update(geometry=None)

        self.finish_services()

        self.source.save(update_fields=['datetime'])

        StopPoint.objects.filter(
            ~Exists(StopUsage.objects.filter(stop=OuterRef('pk'), service__current=True)), active=False
        ).update(active=True)

    def finish_services(self):
        """update/create StopUsages, search_vector and geometry fields"""

        services = Service.objects.filter(id__in=self.service_ids)

        for service in services:
            service.do_stop_usages()

            # using StopUsages
            service.update_search_vector()

            # using routes
            service.update_geometry()

    @cache
    def get_bank_holiday(self, bank_holiday_name):
        return BankHoliday.objects.get_or_create(name=bank_holiday_name)[0]

    def do_bank_holidays(self, holiday_elements, operating_period, operation, calendar_dates):
        if not holiday_elements:
            return

        for element in holiday_elements:
            bank_holiday_name = element.tag
            if bank_holiday_name == 'OtherPublicHoliday':
                calendar_dates.append(
                    get_calendar_date(element.findtext('Date'), operation, element.findtext('Description'))
                )
            else:
                if bank_holiday_name == 'HolidaysOnly':
                    bank_holiday_name = 'AllBankHolidays'
                yield self.get_bank_holiday(bank_holiday_name)

    def get_calendar(self, operating_profile, operating_period):
        calendar_hash = f'{operating_profile.hash}{operating_period}'

        if calendar_hash in self.calendar_cache:
            return self.calendar_cache[calendar_hash]

        calendar_dates = [
            CalendarDate(start_date=date_range.start, end_date=date_range.end,
                         operation=False) for date_range in operating_profile.nonoperation_days
        ]
        for date_range in operating_profile.operation_days:
            calendar_date = CalendarDate(start_date=date_range.start, end_date=date_range.end,
                                         special=True, operation=True)
            difference = date_range.end - date_range.start
            if difference > datetime.timedelta(days=5):
                # looks like this SpecialDaysOperation was meant to be treated like a ServicedOrganisation
                # (school term dates etc)
                calendar_date.special = False
                logger.warning(f'{date_range} is {difference.days} days long')
            calendar_dates.append(calendar_date)

        bank_holidays = {}  # a dictionary to remove duplicates! (non-operation overrides operation)

        for bank_holiday in self.do_bank_holidays(
            holiday_elements=operating_profile.operation_bank_holidays,
            operating_period=operating_period,
            operation=True,
            calendar_dates=calendar_dates
        ):
            bank_holidays[bank_holiday] = CalendarBankHoliday(
                operation=True,
                bank_holiday=bank_holiday
            )

        for bank_holiday in self.do_bank_holidays(
            holiday_elements=operating_profile.nonoperation_bank_holidays,
            operating_period=operating_period,
            operation=False,
            calendar_dates=calendar_dates
        ):
            bank_holidays[bank_holiday] = CalendarBankHoliday(
                operation=False,
                bank_holiday=bank_holiday
            )

        sodt = operating_profile.serviced_organisation_day_type
        summary = []
        non_operation_days = []
        operation_days = []
        if sodt:
            if sodt.non_operation_working_days is sodt.non_operation_holidays:
                pass
            elif sodt.non_operation_working_days:
                if sodt.non_operation_working_days.name:
                    summary.append(f'not {sodt.non_operation_working_days.name} days')
                non_operation_days += sodt.non_operation_working_days.working_days
            elif sodt.non_operation_holidays:
                if sodt.non_operation_holidays.name:
                    summary.append(f'not {sodt.non_operation_holidays.name} holidays')
                non_operation_days += sodt.non_operation_holidays.holidays

            calendar_dates += [
                CalendarDate(start_date=date_range.start, end_date=date_range.end,
                             operation=False)
                for date_range in non_operation_days
            ]

            if sodt.operation_working_days is sodt.operation_holidays:
                pass
            elif sodt.operation_working_days:
                if sodt.operation_working_days.name:
                    summary.append(f'{sodt.operation_working_days.name} days')
                operation_days += sodt.operation_working_days.working_days
            elif sodt.operation_holidays:
                if sodt.operation_holidays.name:
                    summary.append(f'{sodt.operation_holidays.name} holidays')
                operation_days += sodt.operation_holidays.holidays

            calendar_dates += [
                CalendarDate(start_date=date_range.start, end_date=date_range.end,
                             operation=True)
                for date_range in operation_days
            ]

        summary = ', '.join(summary)

        if operating_period.start == operating_period.end:
            if summary:
                summary = f"{summary}, "
            summary = f"{summary}{operating_period.start.strftime('%A %-d %B %Y')} only"

        if summary:
            summary = get_summary(summary)

        calendar = Calendar(
            mon=False,
            tue=False,
            wed=False,
            thu=False,
            fri=False,
            sat=False,
            sun=False,
            start_date=operating_period.start,
            end_date=operating_period.end,
            summary=summary
        )

        for day in operating_profile.regular_days:
            if day == 0:
                calendar.mon = True
            elif day == 1:
                calendar.tue = True
            elif day == 2:
                calendar.wed = True
            elif day == 3:
                calendar.thu = True
            elif day == 4:
                calendar.fri = True
            elif day == 5:
                calendar.sat = True
            elif day == 6:
                calendar.sun = True

        calendar.save()

        weird = False
        for date in calendar_dates:
            date.calendar = calendar
            if date.end_date < date.start_date:
                weird = True
                logger.warning(date)
        if weird:
            calendar_dates = [date for date in calendar_dates if date.end_date >= date.start_date]
        CalendarDate.objects.bulk_create(calendar_dates)

        for bank_holiday in bank_holidays.values():
            bank_holiday.calendar = calendar
        CalendarBankHoliday.objects.bulk_create(bank_holidays.values())

        self.calendar_cache[calendar_hash] = calendar

        return calendar

    def handle_journeys(self, route_code, route_defaults, stops, journeys, txc_service, line_id):
        default_calendar = None

        route, route_created = Route.objects.update_or_create(
            route_defaults, source=self.source, code=route_code
        )

        self.route_ids.add(route.id)

        stop_times = []

        trips = []
        trip_notes = []

        blocks = []

        for journey in journeys:
            calendar = None
            if journey.operating_profile:
                calendar = self.get_calendar(journey.operating_profile, txc_service.operating_period)
            elif journey.journey_pattern.operating_profile:
                calendar = self.get_calendar(journey.journey_pattern.operating_profile, txc_service.operating_period)
            elif txc_service.operating_profile:
                if not default_calendar:
                    default_calendar = self.get_calendar(txc_service.operating_profile, txc_service.operating_period)
                calendar = default_calendar
            else:
                calendar = None

            trip = Trip(
                inbound=journey.journey_pattern.is_inbound(),
                calendar=calendar,
                route=route,
                journey_pattern=journey.journey_pattern.id,
                ticket_machine_code=journey.ticket_machine_journey_code or '',
                sequence=journey.sequencenumber
            )

            if journey.block and journey.block.code:
                if journey.block.code not in self.blocks:
                    trip.block = Block(
                        code=journey.block.code,
                        description=journey.block.description
                    )
                    blocks.append(trip.block)
                    self.blocks[journey.block.code] = trip.block
                else:
                    trip.block = self.blocks[journey.block.code]

            if journey.vehicle_type and journey.vehicle_type.code:
                if journey.vehicle_type.code not in self.vehicle_types:
                    self.vehicle_types[journey.vehicle_type.code], _ = VehicleType.objects.get_or_create(
                        code=journey.vehicle_type.code,
                        description=journey.vehicle_type.description
                    )
                trip.vehicle_type = self.vehicle_types[journey.vehicle_type.code]

            if journey.garage_ref:
                trip.garage = self.garages.get(journey.garage_ref)

            blank = False
            for cell in journey.get_times():
                timing_status = cell.stopusage.timingstatus
                if timing_status is None:
                    timing_status = ''
                    blank = True
                elif len(timing_status) > 3:
                    if timing_status == 'otherPoint':
                        timing_status = 'OTH'
                    elif timing_status == 'timeInfoPoint':
                        timing_status = 'TIP'
                    elif timing_status == 'principleTimingPoint' or timing_status == 'principalTimingPoint':
                        timing_status = 'PTP'
                    else:
                        logger.warning(timing_status)

                stop_time = StopTime(
                    trip=trip,
                    sequence=cell.stopusage.sequencenumber,
                    timing_status=timing_status
                )
                if stop_time.sequence is not None and stop_time.sequence > 32767:  # too big for smallint
                    stop_time.sequence = None

                if cell.stopusage.activity == 'pickUp':
                    stop_time.set_down = False
                elif cell.stopusage.activity == 'setDown':
                    stop_time.pick_up = False
                elif cell.stopusage.activity == 'pass':
                    stop_time.pick_up = False
                    stop_time.set_down = False

                stop_time.departure = cell.departure_time
                if cell.arrival_time != cell.departure_time:
                    stop_time.arrival = cell.arrival_time

                if trip.start is None:
                    trip.start = stop_time.departure_or_arrival()

                atco_code = cell.stopusage.stop.atco_code.upper()
                if atco_code in stops:
                    if type(stops[atco_code]) is str:
                        stop_time.stop_code = stops[atco_code]
                    else:
                        stop_time.stop = stops[atco_code]
                        trip.destination = stop_time.stop
                else:
                    stop_time.stop_code = cell.stopusage.stop.atco_code  # !
                stop_times.append(stop_time)

            # last stop
            if not stop_time.arrival:
                stop_time.arrival = stop_time.departure
                stop_time.departure = None

            trip.end = stop_time.arrival_or_departure()
            trips.append(trip)

            if trip.start == trip.end:
                logger.warning(f"{route_code} trip {trip} takes no time")

            if blank and any(stop_time.timing_status for stop_time in stop_times):
                # not all timing statuses are blank - mark any blank ones as minor
                for stop_time in stop_times:
                    if not stop_time.timing_status:
                        stop_time.timing_status = 'OTH'

            for note in journey.notes:
                note_cache_key = f'{note}:{journey.notes[note]}'
                if note_cache_key in self.notes:
                    note = self.notes[note_cache_key]
                else:
                    note, _ = Note.objects.get_or_create(code=note or '', text=journey.notes[note])
                    self.notes[note_cache_key] = note
                trip_notes.append(Trip.notes.through(trip=trip, note=note))

        Block.objects.bulk_create(blocks)
        for trip in trips:
            trip.block = trip.block

        if not route_created:
            # reuse trip ids if the number and start times haven't changed
            existing_trips = route.trip_set.order_by('id')
            try:
                if len(existing_trips) == len(trips):
                    for i, old_trip in enumerate(existing_trips):
                        if old_trip.start == trips[i].start:
                            trips[i].id = old_trip.id
                        else:
                            logger.info(f"{route_code} {old_trip.start} {trips[i].start}")
                            existing_trips.delete()
                            existing_trips = None
                            break
                else:
                    existing_trips.delete()
                    existing_trips = None
            except IntegrityError:
                existing_trips.delete()
                existing_trips = None
        else:
            existing_trips = None

        if existing_trips:
            Trip.objects.bulk_update(trips, fields=[
                'inbound',
                'journey_pattern',
                'ticket_machine_code',
                'block',
                'destination',
                'calendar',
                'sequence',
                'end',
                'garage',
                'vehicle_type',
            ])
            Trip.notes.through.objects.filter(trip__route=route).delete()
            StopTime.objects.filter(trip__route=route).delete()
        else:
            Trip.objects.bulk_create(trips)

        Trip.notes.through.objects.bulk_create(trip_notes)

        for stop_time in stop_times:
            stop_time.trip = stop_time.trip  # set trip_id
        StopTime.objects.bulk_create(stop_times, batch_size=1000)

    def get_description(self, txc_service):
        description = txc_service.description
        if description:
            if self.source.name.startswith('Stagecoach'):
                description = None
            elif description.isupper():
                description = titlecase(description, callback=initialisms)

        origin = txc_service.origin
        destination = txc_service.destination

        if origin and destination:
            if origin.isupper() and destination.isupper():
                txc_service.origin = origin = titlecase(origin, callback=initialisms)
                txc_service.destination = destination = titlecase(destination, callback=initialisms)

            if not description:
                description = f'{origin} - {destination}'
                vias = txc_service.vias
                if vias:
                    if all(via.isupper() for via in vias):
                        vias = [titlecase(via, callback=initialisms) for via in vias]
                    if len(vias) == 1:
                        via = vias[0]
                        if 'via ' in via:
                            return f"{description} {via}"
                        elif (',' in via or ' and ' in via or '&' in via):
                            return f"{description} via {via}"
                    description = ' - '.join([origin] + vias + [destination])
        return description

    def is_tnds(self):
        return self.source.url.startswith('ftp://ftp.tnds.basemap.co.uk/')

    def should_defer_to_other_source(self, operators: list, line_name: str):
        if self.source.name == 'L':
            return False
        if operators and all(operator.id in self.incomplete_operators for operator in operators):
            services = Service.objects.filter(line_name__iexact=line_name, current=True).exclude(source=self.source)
            if operators[0].parent and operators[0].id not in ('FBRI', 'FECS'):
                services = services.filter(operator__parent=operators[0].parent)
            else:
                services = services.filter(operator__in=operators)
            if services.exists():
                return True

    def get_route_links(self, journeys, transxchange):
        patterns = {
            journey.journey_pattern.id: journey.journey_pattern for journey in journeys
        }
        route_refs = [pattern.route_ref for pattern in patterns.values() if pattern.route_ref]
        if route_refs:
            routes = [transxchange.routes[route_id] for route_id in transxchange.routes if route_id in route_refs]
            for route in routes:
                for section_ref in route.route_section_refs:
                    route_section = transxchange.route_sections[section_ref]
                    for route_link in route_section.links:
                        if route_link.track:
                            yield route_link
        else:
            route_links = {}
            for route_section in transxchange.route_sections.values():
                for route_section_link in route_section.links:
                    route_links[route_section_link.id] = route_section_link
            for journey in journeys:
                if journey.journey_pattern:
                    for section in journey.journey_pattern.sections:
                        for timing_link in section.timinglinks:
                            route_link = route_links[timing_link.route_link_ref]
                            if route_link.track:
                                yield route_link

    def handle_service(self, filename: str, transxchange, txc_service, today, stops):
        if txc_service.operating_period.end and txc_service.operating_period.end < txc_service.operating_period.start:
            logger.warning(
                f"skipping {filename} {txc_service.service_code}: "
                f"end {txc_service.operating_period.end} is before start {txc_service.operating_period.start}"
            )

        operators = self.get_operators(transxchange, txc_service)

        if not operators:
            basename = os.path.basename(filename)  # e.g. 'KCTB_'
            if basename[4] == '_':
                maybe_operator_code = basename[:4]
                if maybe_operator_code.isupper() and maybe_operator_code.isalpha():
                    try:
                        operators = [Operator.objects.get(id=maybe_operator_code)]
                    except Operator.DoesNotExist:
                        pass

        if self.is_tnds():
            if self.source.name != 'L':
                if operators and all(operator.id in self.open_data_operators for operator in operators):
                    return
        elif self.source.name.startswith('Arriva') and 'tfl_' in filename:
            logger.info(f'skipping {filename} {txc_service.service_code} (Arriva London)')
            return
        elif self.source.name.startswith('Stagecoach'):
            if operators and operators[0].parent != 'Stagecoach':
                logger.info(f'skipping {txc_service.service_code} ({operators[0].id})')
                return

        linked_services = []

        description = self.get_description(txc_service)

        if description == 'Origin - Destination':
            description = ''

        if re.match(BODS_SERVICE_CODE_REGEX, txc_service.service_code):
            unique_service_code = txc_service.service_code
        else:
            unique_service_code = None

        line_names = [line.line_name for line in txc_service.lines]

        service = None

        for i, line in enumerate(txc_service.lines):
            # defer to a Bus Open Data type source
            if self.is_tnds() and self.should_defer_to_other_source(operators, line.line_name):
                continue

            if self.source.name.startswith('Stagecoach') and self.preferred_source and Service.objects.filter(
                line_name__iexact=line.line_name, current=True,
                route__source=self.preferred_source
            ).exists():
                continue

            # defer to the better Reading Buses source,
            # unless this service is only present in this worse source
            # (probably a football services)
            if self.source.name.startswith('Reading Buses_') and Service.objects.filter(
                line_name__iexact=line.line_name, current=True,
                route__source__name__in=('Reading Buses', 'Newbury & District')
            ).exists():
                continue

            service_code = None

            q = Q(line_name__iexact=line.line_name)

            existing = None

            if self.source.name.startswith('Sanders') and len(line_names) > 1:
                if i > 0:
                    existing = service
                else:
                    for line_name in line_names:
                        q |= Q(line_name__iexact=line_name)

            if not existing:
                services = Service.objects.order_by('-current', 'id').filter(q)

                if operators:
                    if self.source.name.startswith('Stagecoach'):
                        existing = services.filter(Q(source=self.source) | Q(operator__in=operators))
                    else:
                        existing = services.filter(operator__in=operators)
                else:
                    existing = services

                if len(transxchange.services) == 1:
                    has_stop_time = Exists(StopTime.objects.filter(stop__in=stops, trip__route__service=OuterRef('id')))
                    has_stop_usage = Exists(StopUsage.objects.filter(stop__in=stops, service=OuterRef('id')))
                    has_no_route = ~Exists(Route.objects.filter(service=OuterRef('id')))
                    condition = has_stop_time | (has_stop_usage & has_no_route)
                else:
                    condition = Exists(
                        Route.objects.filter(service_code=txc_service.service_code, service=OuterRef('id'))
                    )
                    if description:
                        condition |= Q(description=description)

                existing = existing.filter(condition).first()

            if self.is_tnds():
                service_code = get_service_code(filename)
                if service_code is None:
                    service_code = txc_service.service_code

                if not existing:
                    # assume service code is at least unique within a TNDS region
                    existing = self.source.service_set.filter(service_code=service_code).first()
            elif unique_service_code:
                service_code = unique_service_code

                if not existing:
                    # try getting by BODS profile compliant service code
                    existing = services.filter(service_code=service_code).first()

            if existing:
                service = existing
            else:
                service = Service()

            service.line_name = line.line_name
            service.date = today
            service.current = True
            service.source = self.source

            journeys = transxchange.get_journeys(txc_service.service_code, line.id)

            if not journeys:
                logger.warning(f'{txc_service.service_code} has no journeys')
                continue

            if txc_service.public_use:
                if txc_service.public_use in ('0', 'false'):
                    if len(journeys) < 5:
                        service.public_use = False
                elif txc_service.public_use in ('1', 'true'):
                    service.public_use = True

            if service_code:
                service.service_code = service_code

            if description:
                service.description = description

            line_brand = line.line_brand
            if txc_service.marketing_name:
                if txc_service.marketing_name == 'CornwallbyKernow':
                    pass
                elif 'tudents only' in txc_service.marketing_name or 'pupils only' in txc_service.marketing_name:
                    service.public_use = False
                else:
                    line_brand = txc_service.marketing_name
                    if line.line_name in line_brand:
                        line_brand_parts = line_brand.split()
                        if line.line_name in line_brand_parts:
                            line_brand_parts.remove(line.line_name)
                            line_brand = ' '.join(line_brand_parts)
            if not line_brand and service.colour and service.colour.name:
                line_brand = service.colour.name
            service.line_brand = line_brand or ''

            if txc_service.mode:
                service.mode = txc_service.mode

            if self.region_id:
                service.region_id = self.region_id

            # inbound and outbound descriptions

            service.outbound_description = ''
            service.inbound_description = ''
            if line.outbound_description != line.inbound_description or txc_service.origin == 'Origin':
                out_desc = line.outbound_description
                in_desc = line.inbound_description

                if out_desc and in_desc and out_desc.isupper() and in_desc.isupper():
                    out_desc = titlecase(out_desc, callback=initialisms)
                    in_desc = titlecase(in_desc, callback=initialisms)

                if out_desc:
                    service.outbound_description = out_desc
                    if not service.description or len(txc_service.lines) > 1:
                        service.description = out_desc
                if in_desc:
                    service.inbound_description = in_desc
                    if not service.description:
                        service.description = in_desc

            if self.service_descriptions:  # NCSD
                outbound_description, inbound_description = self.get_service_descriptions(filename)
                if inbound_description:
                    service.description = service.inbound_description = inbound_description
                if outbound_description:
                    service.description = service.outbound_description = outbound_description

            # does is the service already exist in the database?

            if service.id:
                service_created = False
            else:
                service_created = True
            service.save()

            if not service_created:
                if '_' in service.slug or '-' not in service.slug or existing and not existing.current:
                    service.slug = ''
                    service.save(update_fields=['slug'])

            if operators:
                if service_created:
                    service.operator.set(operators)
                else:
                    if service.id in self.service_ids:
                        service.operator.add(*operators)
                    else:
                        service.operator.set(operators)
            self.service_ids.add(service.id)
            linked_services.append(service.id)

            if txc_service.operating_period.end and txc_service.operating_period.end < today:
                logger.warning(
                    f"{filename}: {txc_service.service_code} end {txc_service.operating_period.end} is in the past"
                )

            journey = journeys[0]

            ticket_machine_service_code = journey.ticket_machine_service_code
            if ticket_machine_service_code and ticket_machine_service_code != line.line_name:
                try:
                    ServiceCode.objects.create(scheme='SIRI', code=ticket_machine_service_code, service=service)
                except IntegrityError:
                    pass

            # a code used in Traveline Cymru URLs:
            if self.source.name == 'W' and '_' not in txc_service.service_code:
                private_code = journey.private_code
                if private_code and ':' in private_code:
                    ServiceCode.objects.update_or_create({
                        'code': private_code.split(':', 1)[0]
                    }, service=service, scheme='Traveline Cymru')

            # timetable data:

            route_defaults = {
                'line_name': line.line_name,
                'line_brand': line_brand,
                'start_date': txc_service.operating_period.start,
                'end_date': txc_service.operating_period.end,
                'service': service,
                'revision_number': transxchange.attributes['RevisionNumber'],
                'service_code': txc_service.service_code,
                'geometry': None
            }

            if txc_service.origin and txc_service.origin != 'Origin':
                route_defaults['origin'] = txc_service.origin
            else:
                route_defaults['origin'] = ''

            if txc_service.destination and txc_service.destination != 'Destination':
                if ' via ' in txc_service.destination:
                    route_defaults['destination'], route_defaults['via'] = txc_service.destination.split(' via ', 1)
                else:
                    route_defaults['destination'] = txc_service.destination
            else:
                route_defaults['destination'] = ''

            if description:
                route_defaults['description'] = description

            if unique_service_code:
                registration = get_registration(unique_service_code)
                if registration:
                    route_defaults['registration'] = registration

            if transxchange.route_sections:
                if service_created:
                    existing_route_links = {}
                else:
                    existing_route_links = {
                        (link.from_stop_id, link.to_stop_id): link for link in service.routelink_set.all()
                    }
                route_links_to_update = {}
                route_links_to_create = {}
                for route_link in self.get_route_links(journeys, transxchange):
                    from_stop = stops.get(route_link.from_stop)
                    to_stop = stops.get(route_link.to_stop)
                    if type(from_stop) is StopPoint and type(to_stop) is StopPoint:
                        key = (route_link.from_stop, route_link.to_stop)
                        if key in existing_route_links:
                            if key not in existing_route_links:
                                route_links_to_update[key].geometry = route_link.track
                        else:
                            route_links_to_create[key] = RouteLink(
                                from_stop_id=route_link.from_stop,
                                to_stop_id=route_link.to_stop,
                                geometry=route_link.track,
                                service=service
                            )

                RouteLink.objects.bulk_update(route_links_to_update.values(), ['geometry'])
                RouteLink.objects.bulk_create(route_links_to_create.values())

            route_code = filename
            if len(transxchange.services) > 1:
                route_code += f'#{txc_service.service_code}'
            if len(txc_service.lines) > 1:
                route_code += f'#{line.id}'

            self.handle_journeys(route_code, route_defaults, stops, journeys, txc_service, line.id)

        if len(linked_services) > 1:
            for i, from_service in enumerate(linked_services):
                for i, to_service in enumerate(linked_services[i+1:]):
                    kwargs = {
                        'from_service_id': from_service,
                        'to_service_id': to_service,
                    }
                    if not ServiceLink.objects.filter(**kwargs).exists():
                        ServiceLink.objects.create(**kwargs, how='also')

    @staticmethod
    def do_stops(transxchange_stops: dict) -> dict:
        stops = list(transxchange_stops.keys())
        for atco_code in transxchange_stops:
            if len(atco_code) == 11 and atco_code.isdigit() and atco_code[0] != "0" and atco_code[2] == "0":
                stops.append(f"0{atco_code}")

        stops = StopPoint.objects.annotate(
            atco_code_upper=Upper('atco_code')
        ).filter(atco_code_upper__in=stops).only('atco_code')

        stops = {
            stop.atco_code_upper: stop
            for stop in stops
        }

        for atco_code, stop in transxchange_stops.items():
            atco_code_upper = atco_code.upper()
            if atco_code_upper not in stops:
                if atco_code.isdigit() and f"0{atco_code}" in stops:  # "36006002112" = "036006002112"
                    logger.warning(f"{atco_code} 0{atco_code}")
                    stops[atco_code_upper] = stops[f"0{atco_code}"]
                else:
                    # logger.warning(f"{atco_code} {stop}")
                    stops[atco_code.upper()] = str(stop)[:255]

        return stops

    def do_garages(self, garages):
        for garage_code in garages:
            garage = garages[garage_code]

            name = garage.findtext('GarageName', '')
            if name == f"Garage '{garage_code}'":  # "Garage 'KB'"
                name = ""
            else:
                name = name.removesuffix(' Bus Depot')
                name = name.removesuffix(' depot').removesuffix(' Depot').removesuffix(' DEPOT')
                name = name.removesuffix(' garage').removesuffix(' Garage').removesuffix(' GARAGE').strip()

            if garage_code not in self.garages or self.garages[garage_code].name != name:
                garage = Garage.objects.filter(code=garage_code, name__iexact=name).first()
                if garage is None:
                    garage = Garage.objects.create(code=garage_code, name=name)
                self.garages[garage_code] = garage

    def handle_file(self, open_file, filename: str):
        transxchange = TransXChange(open_file)

        if not transxchange.journeys:
            logger.warning(f'{filename} has no journeys')
            return

        self.blocks = {}
        self.vehicle_types = {}

        today = self.source.datetime.date()

        stops = self.do_stops(transxchange.stops)

        self.do_garages(transxchange.garages)

        for txc_service in transxchange.services.values():
            self.handle_service(filename, transxchange, txc_service, today, stops)
