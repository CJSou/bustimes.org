"""
Command for importing transport services.

So far, all services in the SE, EA, Y and NCSD regions can be imported without
known errors.

Usage:

    ./manage.py import_services EA.zip [EM.zip etc]
"""

import re
import zipfile
import csv
import xml.etree.cElementTree as ET
from datetime import datetime
from titlecase import titlecase

from django.core.management.base import BaseCommand
from django.db import transaction

from timetables.timetable import Timetable
from ...models import Operator, StopPoint, Service, StopUsage


# map names to operator IDs where there is no correspondence between the NOC DB and TNDS:
SPECIAL_OPERATOR_TRADINGNAMES = {
    'Arriva Northumbria': 'ANUM',
    'Southwold Town Council': 'SWTC',
    'H.C.Chambers & Son': 'CHMB',
    'Bungay and Beccles Area CT': 'BBCT',
    'Stowmarket Minibus & Coach Hire': 'MBCH',
    'Harwich Harbour Ferry': 'HHFS',
    'Halesworth Area Community Transport': 'HACT',
    'Dartmouth Steam Railway And River Boat Company': 'DRMR',
    'Borderbus': 'BDRB',
    'ARRIVA LONDON NORTH LIMITED': 'ALNO',
    'ARRIVA LONDON SOUTH LIMITED': 'ALSO',
    'ARRIVA THE SHIRES LIMITED': 'ASES',
    'ARRIVA KENT THAMESIDE LIMITED': 'AMTM',
    'METROBUS LIMITED': 'METR',
    'EAST LONDON BUS & COACH COMPANY LIMITED': 'ELBG',
    'SOUTH EAST LONDON & KENT BUS COMPANY LTD': 'SELK',
    'TRAMTRACK CROYDON LTD': 'TRAM',
    'Westminster Passenger Service Association': 'WPSA',
    'First Cornwall': 'FCWL',
    'IoW Floating Bridge': 'IOWC',
    'Ladies Only Travel': 'YLOT',
    'LONDON SOVEREIGN LIMITED': 'LSOV',
    'ABELLIO LONDON LIMITED': 'ABLO',
    'ABELLIO LONDON (WEST) LIMITED': 'ABLO',
    'TOWER TRANSIT LIMITED': 'TOTR',
    'UNO BUSES LIMITED': 'UNOE',
    'C T PLUS LIMITED': 'NCTP',
    'Gloucestershire': 'SCGL',
    'BLUE TRIANGLE BUSES LIMITED': 'BTRI',
    'METROLINE WEST LIMITED': 'MTLN',
    'LONDON CENTRAL BUS COMPANY LIMITED': 'LONC',
    'SULLIVAN BUS & COACH LIMITED': 'SULV',
    'Notts & Derby': 'NDTR',
    'LIVERPOOL CITY SIGHTS': 'CISI',
    'WDC': 'WDCB',  # Western Dales Community Bus
    'Rothbury Securities Ltd': 'ROTH',
    'KL': 'KELC',  # Keswick Launch Company
    'Carters Heritage Buses': 'CTCS',
    'King Harry Ferry Co': 'KHFC',
    'Fal River Ferries': 'KHFC'
}
# map OperatorCodes to operator IDs (ditto, where there is no TradingName):
SPECIAL_OPERATOR_CODES = {
    'HIB': 'HIMB',  # Holy Island Minibus
    '1866': 'BPTR',  # Burnley & Pendle
    '2152': 'RSTY',  # R S Tyrer & Sons
    '2916': 'SPCT',  # South Pennine Community Transport
    'RB1': 'RBRO',  # Richards Bros
    'ACY': 'ACYM',  # Arriva Cymru/Wales
    'AM0': 'AMID',  # Arriva Midlands
    'RMB': 'RMBL',  # Routemaster Buses Ltd
    'JO1': 'JTMT',  # John's Travel (Merthyr Tydfil)
    'CO': 'CFSV',  # Coniston Launch/Ferry
    'CL': 'CFSV',  # Coniston Launch/Ferry
    'SGI': 'SGIL',  # Steel Group Investments Limited
    'EYM': 'EYMS',  # East Yorkshire Motor Services
    'WINF': 'WMLC',  # Windermere Lake Cruises/Ferry
    'DPC': 'DPCE',  # (Don) Prentice (Coaches)
    'PCV': 'PCVN',  # (Peter) Canavan (Travel)
    'RGJ': 'RGJS',  # R G Jamieson & Son
    'DAM': 'DAMC',  # D A & A J MacLean
    'ADD': 'ADDI',  # Addison News/of Callendar
    'HBSY': 'YTIG',  # Huddersfield Bus Company/Yorkshire Tiger
    'ALI': 'AMDD',   # Alasdair MacDonald
    'EWE': 'EWEN',   # Ewens Coach Hire
}


class Command(BaseCommand):

    # see https://docs.python.org/2/library/xml.etree.elementtree.html#parsing-xml-with-namespaces
    ns = {'txc': 'http://www.transxchange.org.uk/'}

    now = datetime.today()

    description_regex = re.compile(r'.+,([^ ].+)$')

    @staticmethod
    def add_arguments(parser):
        parser.add_argument('filenames', nargs='+', type=str)

    @staticmethod
    def infer_from_file_name(file_name):
        """
        Given a file name like 'ea_21-45A-_-y08-1.xml',
        returns a (net, service_code, line_ver) tuple like ('ea', 'ea_21-45A-_-y08', '1')

        Given any other sort of file name, returns ('', None, None)
        """
        parts = file_name.split('-')  # ['ea_21', '3', '_', '1']
        if len(parts) == 5:
            net = parts[0].split('_')[0]
            if len(net) <= 3 and net.islower():
                return (net, '-'.join(parts[:-1]), parts[-1][:-4])
        return ('', None, None)

    @classmethod
    def sanitize_description_part(cls, part):
        """
        Given an oddly formatted part like 'Bus Station bay 5,Blyth',
        returns a shorter, more normal version like 'Blyth'
        """
        sanitized_part = cls.description_regex.match(part.strip())
        return sanitized_part.group(1) if sanitized_part is not None else part

    @classmethod
    def sanitize_description(cls, name):
        """
        Given an oddly formatted description from the North East,
        like 'Bus Station bay 5,Blyth - Grange Road turning circle,Widdrington Station',
        returns a shorter, more normal version like
        'Blyth - Widdrington Station'
        """

        parts = [cls.sanitize_description_part(part) for part in name.split(' - ')]
        return ' - '.join(parts)

    @classmethod
    def get_operator_name(cls, operator_element):
        "Given an Operator element, returns the operator name or None"

        for element_name in ('TradingName', 'OperatorNameOnLicence', 'OperatorShortName'):
            element = operator_element.find('txc:%s' % element_name, cls.ns)
            if element is not None and element.text is not None:
                return element.text.replace('&amp;', '&')

    @classmethod
    def get_operator_code(cls, operator_element):
        "Given an Operator element, returns the operator code or None"

        for element_name in ('National', ''):
            element = operator_element.find('txc:%sOperatorCode' % element_name, cls.ns)
            if element is not None:
                return element.text

    @classmethod
    def get_operator(cls, operator_element):
        "Given an Operator element, returns an Operator object."

        # Get by national operator code
        operator_code = cls.get_operator_code(operator_element)
        if len(operator_code) > 2 or operator_code == 'BR':
            possible_operators = Operator.objects.filter(id=operator_code)
            if possible_operators:
                return possible_operators[0]

        # Get by name
        operator_name = cls.get_operator_name(operator_element)

        if operator_name in ('Replacement Service', 'UNKWN'):
            return None

        if operator_name in SPECIAL_OPERATOR_TRADINGNAMES:
            return Operator.objects.get(id=SPECIAL_OPERATOR_TRADINGNAMES[operator_name])

        if operator_code in SPECIAL_OPERATOR_CODES:
            return Operator.objects.get(id=SPECIAL_OPERATOR_CODES[operator_code])

        possible_operators = Operator.objects.filter(name__istartswith=operator_name)
        if len(possible_operators) == 1:
            return possible_operators[0]

        print ET.tostring(operator_element)

    @classmethod
    def get_line_name_and_brand(cls, service_element, file_name):
        line_name = service_element.find('txc:Lines', cls.ns)[0][0].text
        if '|' in line_name:
            line_name_parts = line_name.split('|', 1)
            line_name = line_name_parts[0]
            line_brand = line_name_parts[1]
        else:
            line_brand = ''

        if len(line_name) > 64:
            print 'Name "%s" is too long in %s' % (line_name, file_name)
            line_name = line_name[:64]

        return (line_name, line_brand)

    @classmethod
    def do_service(cls, root, region_id, service_descriptions=None):

        file_name = root.attrib['FileName']

        for service_element in root.find('txc:Services', cls.ns):

            line_name, line_brand = cls.get_line_name_and_brand(
                service_element, file_name
            )

            mode_element = service_element.find('txc:Mode', cls.ns)
            if mode_element is not None:
                mode = mode_element.text
            else:
                mode = ''

            # service operators:
            # (doing this preliminary bit now, to make getting NCSD descriptions possible)

            operators_element = root.find('txc:Operators', cls.ns)
            operators = map(cls.get_operator, operators_element)
            operators = filter(None, operators)

            # service description:

            description_element = service_element.find('txc:Description', cls.ns)
            if description_element is not None:
                description = description_element.text
            elif service_descriptions is not None:
                description = service_descriptions.get(operators[0].id + line_name, '')
            else:
                print '%s is missing a name' % file_name
                description = ''

            if description.isupper():
                description = titlecase(description)

            if region_id == 'NE':
                description = cls.sanitize_description(description)

            if len(description) > 128:
                print 'Description "%s" is too long in %s' % (description, file_name)
                description = description[:128]

            # net and service code:

            net, service_code, line_ver = cls.infer_from_file_name(file_name)
            if service_code is None:
                service_code = service_element.find('txc:ServiceCode', cls.ns).text

            # stops:

            stop_elements = root.find('txc:StopPoints', cls.ns)
            stop_ids = [stop.find('txc:StopPointRef', cls.ns).text for stop in stop_elements]
            stops = StopPoint.objects.in_bulk(stop_ids)

            try:
                timetable = Timetable(root)

                show_timetable = True
                for grouping in timetable.groupings:
                    show_timetable = show_timetable and (len(grouping.journeys) < 60 or len(filter(None, grouping.rows[0].times)) < 40)

                stop_usages = [
                    StopUsage(service_id=service_code, stop_id=row.part.stop.atco_code, direction='outbound', order=i, timing_status=row.part.timingstatus)
                    for i, row in enumerate(timetable.groupings[0].rows)
                    if stops.get(row.part.stop.atco_code)
                ]
                stop_usages += [
                    StopUsage(service_id=service_code, stop_id=row.part.stop.atco_code, direction='inbound', order=i, timing_status=row.part.timingstatus)
                    for i, row in enumerate(timetable.groupings[1].rows)
                    if stops.get(row.part.stop.atco_code)
                ]
            except (AttributeError, IndexError) as e:
                print e, file_name
                show_timetable = False
                stop_usages = [StopUsage(service_id=service_code, stop_id=stop, order=0) for stop in stops]


            # service:

            service = Service.objects.update_or_create(
                service_code=service_code,
                defaults=dict(
                    line_name=line_name,
                    line_brand=line_brand,
                    mode=mode,
                    description=description,
                    net=net,
                    line_ver=line_ver,
                    region_id=region_id,
                    date=root.attrib['ModificationDateTime'][:10],
                    current=True,
                    show_timetable=show_timetable
                )
            )[0]

            service.stops.clear()
            StopUsage.objects.bulk_create(stop_usages)
            service.operator.add(*operators)

    @classmethod
    @transaction.atomic
    def handle_region(cls, archive_name):
        region_id = archive_name.split('/')[-1][:-4]
        if region_id == 'NCSD':
            region_id = 'GB'

        archive = zipfile.ZipFile(archive_name)

        Service.objects.filter(region_id=region_id).update(current=False)

        # the NCSD has service descriptions in a separate file:
        if 'IncludedServices.csv' in archive.namelist():
            with archive.open('IncludedServices.csv') as csv_file:
                reader = csv.DictReader(csv_file)
                # e.g. {'NATX323': 'Cardiff - Liverpool'}
                service_descriptions = {row['Operator'] + row['LineName']: row['Description'] for row in reader}
        else:
            service_descriptions = None

        for i, file_name in enumerate(archive.namelist()):
            if i % 100 == 0:
                print i

            if file_name.endswith('.xml'):
                root = ET.parse(archive.open(file_name)).getroot()
                cls.do_service(root, region_id, service_descriptions=service_descriptions)

    @classmethod
    def handle(cls, *args, **options):
        for archive_name in options['filenames']:
            print archive_name
            cls.handle_region(archive_name)
