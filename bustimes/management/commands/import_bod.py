"""Import timetable data "fresh from the cow"
"""
import os
import requests
import time
from ciso8601 import parse_datetime
from email.utils import parsedate_to_datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from busstops.models import DataSource, Service, Operator
from .import_gtfs import download_if_modified, write_zip_file
from .import_transxchange import Command as TransXChangeCommand
from .import_passenger import handle_file
from ...models import Route, Calendar


session = requests.Session()


def clean_up(operators, sources):
    Route.objects.filter(service__operator__in=operators).exclude(source__in=sources).delete()
    Service.objects.filter(operator__in=operators, current=True, route=None).update(current=False)
    Calendar.objects.filter(trip=None).delete()


def get_command():
    command = TransXChangeCommand()
    command.undefined_holidays = set()
    command.notes = {}
    command.corrections = {}

    return command


# like download_if_modified but different...
def download_if_changed(path, url):
    headers = {}
    modified = True
    if os.path.exists(path):
        last_modified = time.localtime(os.path.getmtime(path))
        headers['if-modified-since'] = time.asctime(last_modified)

        response = requests.head(url, headers=headers)
        if response.status_code == 304:
            modified = False

    if modified:
        response = requests.get(url, headers=headers, stream=True)

        if response.status_code == 304:
            modified = False
        else:
            write_zip_file(path, response)

    if 'x-amz-meta-cb-modifiedtime' in response.headers:
        last_modified = response.headers['x-amz-meta-cb-modifiedtime']
    elif 'last-modified' in response.headers:
        last_modified = response.headers['last-modified']
    last_modified = parsedate_to_datetime(last_modified)

    return modified, last_modified


def bus_open_data(api_key):
    command = get_command()

    for operator_id, region_id, operators in settings.BOD_OPERATORS:
        command.operators = operators
        command.region_id = region_id
        command.service_descriptions = {}
        command.service_codes = set()
        command.calendar_cache = {}

        sources = []

        url = 'https://data.bus-data.dft.gov.uk/api/v1/dataset/'
        params = {
            'api_key': api_key,
            'noc': operator_id,
            'status': ['published', 'expiring']
        }

        while url:
            response = session.get(url, params=params)
            json = response.json()

            for result in json['results']:
                filename = result['name']
                url = result['url']
                path = os.path.join(settings.DATA_DIR, filename)

                modified = parse_datetime(result['modified'])

                command.source, created = DataSource.objects.get_or_create({'name': filename}, url=url)

                if command.source.datetime != modified:
                    print(response.url, filename)
                    command.source.datetime = modified
                    download_if_modified(path, url)
                    handle_file(command, filename)

                    if not created:
                        command.source.name = filename
                    command.source.save(update_fields=['name', 'datetime'])

                    print(' ', Operator.objects.filter(service__route__source=command.source).distinct().values('id'))

                    command.mark_old_services_as_not_current()

                sources.append(command.source)

            url = json['next']
            params = None

        if sources:
            clean_up(operators.values(), sources)


def first():
    command = get_command()

    for operator, region_id, operators in settings.FIRST_OPERATORS:
        filename = operator + '.zip'
        url = 'http://travelinedatahosting.basemap.co.uk/data/first/' + filename
        modified = download_if_modified(os.path.join(settings.DATA_DIR, filename), url)

        if modified:
            print(operator)

            command.operators = operators
            command.region_id = region_id
            command.service_descriptions = {}
            command.service_codes = set()
            command.calendar_cache = {}

            command.source, created = DataSource.objects.get_or_create({'name': operator}, url=url)
            command.source.datetime = timezone.now()

            handle_file(command, filename)

            command.mark_old_services_as_not_current()

            clean_up(operators.values(), [command.source])

            command.source.save(update_fields=['datetime'])

            print(' ', command.source.route_set.order_by('end_date').distinct('end_date').values('end_date'))
            print(' ', Operator.objects.filter(service__route__source=command.source).distinct().values('id'))


def stagecoach():
    command = get_command()

    for region_id, noc, operator, operators in settings.STAGECOACH_OPERATORS:
        filename = f'stagecoach-{noc}-route-schedule-data-transxchange.zip'
        url = f'https://opendata.stagecoachbus.com/{filename}'
        path = os.path.join(settings.DATA_DIR, filename)

        command.source, created = DataSource.objects.get_or_create({'name': operator}, url=url)

        modified, last_modified = download_if_changed(path, url)

        if modified and command.source.datetime and command.source.datetime >= last_modified:
            modified = False

        if modified:
            print(operator)

            command.operators = operators
            command.region_id = region_id
            command.service_descriptions = {}
            command.service_codes = set()
            command.calendar_cache = {}

            # avoid importing old data
            command.source.datetime = timezone.now()

            handle_file(command, filename)

            command.mark_old_services_as_not_current()

            clean_up(command.operators.values(), [command.source])

            command.source.datetime = last_modified
            command.source.save(update_fields=['datetime'])

            print(' ', command.source.route_set.order_by('end_date').distinct('end_date').values('end_date'))
            print(' ', {o['id']: o['id'] for o in
                  Operator.objects.filter(service__route__source=command.source).distinct().values('id')})


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('api_key', type=str)

    def handle(self, api_key, **options):

        stagecoach()

        bus_open_data(api_key)

        first()
