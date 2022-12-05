"""Import timetable data "fresh from the cow"
"""
import hashlib
import logging
import xml.etree.cElementTree as ET
import zipfile
from io import StringIO
from pathlib import Path

import requests
from ciso8601 import parse_datetime
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DataError, IntegrityError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from busstops.models import DataSource, Operator, Service

from ...download_utils import download, download_if_changed
from ...models import Route, TimetableDataSource
from .import_transxchange import Command as TransXChangeCommand

logger = logging.getLogger(__name__)
session = requests.Session()


def clean_up(operators, sources, incomplete=False):
    service_operators = Service.operator.through.objects.filter(
        service=OuterRef("service")
    )
    routes = Route.objects.filter(
        ~Q(source__in=sources),
        ~Q(source__name__in=("L", "bustimes.org")),
        Exists(service_operators.filter(operator__in=operators)),
        ~Exists(
            service_operators.filter(~Q(operator__in=operators))
        ),  # exclude joint services
    )
    if incomplete:  # leave other sources alone
        routes = routes.filter(source__url__contains="bus-data.dft.gov.uk")
    try:
        routes.delete()
    except IntegrityError:
        routes.delete()
    Service.objects.filter(
        ~Q(source__name="bustimes.org"),
        operator__in=operators,
        current=True,
        route=None,
    ).update(current=False)


def get_operator_ids(source):
    operators = (
        Operator.objects.filter(service__route__source=source).distinct().values("noc")
    )
    return [operator["noc"] for operator in operators]


def get_command():
    command = TransXChangeCommand()
    command.set_up()
    return command


def get_sha1(path):
    sha1 = hashlib.sha1()
    with path.open("rb") as open_file:
        while True:
            data = open_file.read(65536)
            if not data:
                return sha1.hexdigest()
            sha1.update(data)


def handle_file(command, path, qualify_filename=False):
    # the downloaded file might be plain XML, or a zipped archive - we just don't know yet
    full_path = settings.DATA_DIR / path

    try:
        with zipfile.ZipFile(full_path) as archive:
            for filename in archive.namelist():
                if filename.endswith(".csv") or "__MACOSX/" in filename:
                    continue
                with archive.open(filename) as open_file:
                    if qualify_filename:
                        # source has multiple versions (Passsenger) so add a prefix like 'gonortheast_123.zip/'
                        filename = str(Path(path) / filename)
                    try:
                        try:
                            command.handle_file(open_file, filename)
                        except ET.ParseError:
                            open_file.seek(0)
                            content = open_file.read().decode("utf-16")
                            fake_file = StringIO(content)
                            command.handle_file(fake_file, filename)
                    except (ET.ParseError, ValueError, AttributeError, DataError) as e:
                        if filename.endswith(".xml"):
                            logger.info(filename)
                            logger.error(e, exc_info=True)
    except zipfile.BadZipFile:
        # plain XML
        with full_path.open() as open_file:
            if qualify_filename:
                filename = path
            else:
                filename = ""
            try:
                command.handle_file(open_file, filename)
            except (AttributeError, DataError) as e:
                logger.error(e, exc_info=True)


def get_bus_open_data_paramses(sources, api_key):
    searches = [
        source.search for source in sources if " " in source.search
    ]  # e.g. 'TM Travel'
    nocs = [
        source.search for source in sources if " " not in source.search
    ]  # e.g. 'TMTL'

    # chunk – we will search for nocs 20 at a time
    nocses = [nocs[i : i + 20] for i in range(0, len(nocs), 20)]

    base_params = {
        "api_key": api_key,
        "status": "published",
    }

    # and search phrases one at a time
    for search in searches:
        yield {
            **base_params,
            "search": search,
        }

    for nocs in nocses:
        yield {**base_params, "noc": ",".join(nocs)}


def bus_open_data(api_key, specific_operator):
    assert len(api_key) == 40

    command = get_command()

    url_prefix = "https://data.bus-data.dft.gov.uk"
    path_prefix = settings.DATA_DIR / "bod"
    if not path_prefix.exists():
        path_prefix.mkdir()

    datasets = []

    timetable_data_sources = TimetableDataSource.objects.filter(url="", active=True)
    if specific_operator:
        timetable_data_sources = timetable_data_sources.filter(name=specific_operator)

    for params in get_bus_open_data_paramses(timetable_data_sources, api_key):
        url = f"{url_prefix}/api/v1/dataset/"
        while url:
            response = session.get(url, params=params)
            json = response.json()
            results = json["results"]
            if not results:
                logger.warning(f"no results: {response.url}")
            for dataset in results:
                dataset["modified"] = parse_datetime(dataset["modified"])
                datasets.append(dataset)
            url = json["next"]
            params = None

    all_source_ids = []

    for source in timetable_data_sources:
        if " " in source.search:
            operator_datasets = [
                item
                for item in datasets
                if source.search in item["name"] or source.search in item["description"]
            ]
        else:
            operator_datasets = [
                item for item in datasets if source.search in item["noc"]
            ]

        command.region_id = source.region_id

        sources = []
        service_ids = set()

        operators = source.operators.values_list("noc", flat=True)

        for dataset in operator_datasets:
            command.source = DataSource.objects.filter(url=dataset["url"]).first()
            if (
                not command.source
                and " " not in source.search
                and len(operator_datasets) == 1
            ):
                name_prefix = dataset["name"].split("_", 1)[0]
                # if old dataset was made inactive, reuse id
                command.source = DataSource.objects.filter(
                    name__startswith=f"{name_prefix}_"
                ).first()
            if not command.source:
                command.source = DataSource.objects.create(
                    name=dataset["name"], url=dataset["url"]
                )
            command.source.name = dataset["name"]
            command.source.url = dataset["url"]
            command.source.source = source

            sources.append(command.source)

            if specific_operator or command.source.datetime != dataset["modified"]:

                logger.info(dataset["name"])

                filename = str(command.source.id)
                path = path_prefix / filename

                command.service_ids = set()
                command.route_ids = set()
                command.garages = {}

                command.source.datetime = dataset["modified"]

                download(path, command.source.url)

                handle_file(command, path)

                command.mark_old_services_as_not_current()

                command.source.sha1 = get_sha1(path)
                command.source.save()

                operator_ids = get_operator_ids(command.source)
                logger.info(f"  {operator_ids}")
                logger.info(
                    f"  unexpected: {[o for o in operator_ids if o not in operators]} (not in {operators})"
                )

                service_ids |= command.service_ids

        # delete routes from any sources that have been made inactive
        for o in operators:
            if Service.objects.filter(
                Q(source__in=sources) | Q(route__source__in=sources),
                current=True,
                operator=o,
            ).exists():
                clean_up([o], sources, not source.complete)
            elif Service.objects.filter(
                current=True, operator=o, route__source__url__startswith=url_prefix
            ).exists():
                logger.warning(f"{o} has no current data")

        command.service_ids = service_ids
        command.finish_services()
        all_source_ids += [source.id for source in sources]

    if not specific_operator:
        to_delete = DataSource.objects.filter(
            ~Q(id__in=all_source_ids),
            ~Exists(Route.objects.filter(source=OuterRef("id"))),
            url__startswith=f"{url_prefix}/timetable/",
        )
        if to_delete:
            logger.info(to_delete)
            logger.info(to_delete.delete())

    command.debrief()


def ticketer(specific_operator=None):
    command = get_command()

    base_dir = settings.DATA_DIR / "ticketer"

    if not base_dir.exists():
        base_dir.mkdir()

    timetable_data_sources = TimetableDataSource.objects.filter(
        url__startswith="https://opendata.ticketer.com", active=True
    )
    if specific_operator:
        timetable_data_sources = timetable_data_sources.filter(
            operators=specific_operator
        )

    for source in timetable_data_sources:
        path = Path(source.url)

        filename = f"{path.parts[3]}.zip"
        path = base_dir / filename
        command.source, created = DataSource.objects.get_or_create(
            {"name": source.name}, url=source.url
        )
        command.source.source = source
        command.garages = {}

        modified, last_modified = download_if_changed(path, source.url)

        if (
            specific_operator
            or not command.source.datetime
            or last_modified > command.source.datetime
        ):
            logger.info(f"{source.url} {last_modified}")

            sha1 = get_sha1(path)

            existing = DataSource.objects.filter(url__contains=".gov.uk", sha1=sha1)
            if existing:
                # hash matches that hash of some BODS data
                logger.info("  skipping, {sha1=} matches {existing=}")
            else:
                command.region_id = source.region_id
                command.service_ids = set()
                command.route_ids = set()

                # for "end date is in the past" warnings
                command.source.datetime = timezone.now()

                handle_file(command, path)

                command.mark_old_services_as_not_current()

                nocs = list(source.operators.values_list("noc", flat=True))

                clean_up(nocs, [command.source])

                command.finish_services()

                logger.info(
                    f"  ⏱️ {timezone.now() - command.source.datetime}"
                )  # log time taken

            command.source.sha1 = sha1
            command.source.datetime = last_modified
            command.source.save()

            logger.info(
                f"  {command.source.route_set.order_by('end_date').distinct('end_date').values('end_date')}"
            )
            logger.info(f"  {get_operator_ids(command.source)}")

    command.debrief()


def do_stagecoach_source(command, last_modified, filename, nocs):
    logger.info(f"{command.source.url} {last_modified}")

    # avoid importing old data
    command.source.datetime = timezone.now()

    handle_file(command, filename)

    command.mark_old_services_as_not_current()

    logger.info(f"  ⏱️ {timezone.now() - command.source.datetime}")  # log time taken

    command.source.datetime = last_modified
    command.source.save()

    logger.info(
        f"  {command.source.route_set.order_by('end_date').distinct('end_date').values('end_date')}"
    )
    operators = get_operator_ids(command.source)
    logger.info(f"  {operators=}")
    logger.info(f"  {[o for o in operators if o not in nocs]} not in {nocs}")


def stagecoach(operator=None):
    command = get_command()

    timetable_data_sources = TimetableDataSource.objects.filter(
        url__startswith="https://opendata.stagecoachbus.com", active=True
    )
    if operator:
        timetable_data_sources = timetable_data_sources.filter(operators=operator)

    for source in timetable_data_sources:

        command.region_id = source.region_id
        command.service_ids = set()
        command.route_ids = set()
        command.garages = {}

        nocs = list(source.operators.values_list("noc", flat=True))

        sources = []  # one (TXC 2.1) or two (2.1 and 2.4) sources

        command.preferred_source = None

        for url in source.url.split():
            filename = Path(url).name
            path = settings.DATA_DIR / filename

            command.source, _ = DataSource.objects.get_or_create(
                {"name": source.name}, url=url
            )
            sources.append(command.source)

            modified, last_modified = download_if_changed(path, url)

            sha1 = get_sha1(path)

            if modified:
                # use sha1 checksum to check if file has really changed -
                # last_modified seems to change every night
                # even when contents stay the same
                if sha1 == command.source.sha1 or not command.source.older_than(
                    last_modified
                ):
                    modified = False

            command.source.sha1 = sha1

            if modified or operator:
                do_stagecoach_source(command, last_modified, filename, nocs)

            command.preferred_source = command.source

        clean_up(nocs, sources)
        command.finish_services()

    command.debrief()


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument("api_key", type=str)
        parser.add_argument("operator", type=str, nargs="?")

    def handle(self, api_key, operator, **options):
        if api_key == "stagecoach":
            stagecoach(operator)
        elif api_key == "ticketer":
            ticketer(operator)
        else:
            bus_open_data(api_key, operator)
