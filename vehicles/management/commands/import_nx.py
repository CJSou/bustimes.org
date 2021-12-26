import ciso8601
from time import sleep
from datetime import timedelta
from pytz.exceptions import AmbiguousTimeError, NonExistentTimeError
from requests import RequestException
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.db.models import Exists, OuterRef
from busstops.models import Service
from bustimes.models import get_calendars, Trip
from ...models import VehicleLocation, VehicleJourney
from ..import_live_vehicles import ImportLiveVehiclesCommand


def parse_datetime(string):
    datetime = ciso8601.parse_datetime(string)
    try:
        return timezone.make_aware(datetime)
    except AmbiguousTimeError:
        return timezone.make_aware(datetime, is_dst=True)
    except NonExistentTimeError:
        return timezone.make_aware(datetime + timedelta(hours=1))


class Command(ImportLiveVehiclesCommand):
    source_name = 'National coach code'
    operators = ['NATX', 'NXSH', 'NXAP', 'WAIR']
    url = 'https://coachtracker.nationalexpress.com/api/eta/routes/{}/{}'
    sleep = 1.5

    @staticmethod
    def get_datetime(item):
        return parse_datetime(item['live']['timestamp']['dateTime'])

    def get_items(self):
        now = self.source.datetime
        time_since_midnight = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second,
                                        microseconds=now.microsecond)
        trips = Trip.objects.filter(calendar__in=get_calendars(now),
                                    start__lte=time_since_midnight + timedelta(minutes=5),
                                    end__gte=time_since_midnight - timedelta(minutes=30))
        has_trips = Exists(trips.filter(route__service=OuterRef('id')))
        services = Service.objects.filter(has_trips, operator__in=self.operators)
        for service in services.values('line_name'):
            line_name = service['line_name']
            for direction in 'OI':
                try:
                    res = self.session.get(self.url.format(line_name, direction), timeout=5)
                except RequestException as e:
                    print(e)
                    continue
                if not res.ok:
                    print(res.url, res)
                    continue
                if direction != res.json()['dir']:
                    print(res.url)
                for item in res.json()['services']:
                    if item['live']:
                        yield(item)
            self.save()
            sleep(self.sleep)

    def get_vehicle(self, item):
        return self.vehicles.get_or_create(source=self.source, operator_id=self.operators[0],
                                           code=item['live']['vehicle'])

    def get_journey(self, item, vehicle):
        journey = VehicleJourney(
            datetime=parse_datetime(item['startTime']['dateTime']),
            route_name=item['route']
        )

        latest_journey = vehicle.latest_journey
        if latest_journey and journey.datetime == latest_journey.datetime:
            if journey.route_name == latest_journey.route_name and latest_journey.service_id:
                return latest_journey
            journey = latest_journey
        else:
            try:
                journey = VehicleJourney.objects.get(vehicle=vehicle, datetime=journey.datetime)
            except VehicleJourney.DoesNotExist:
                pass

        journey.destination = item['arrival']
        if item['dir'] == "O":
            journey.direction = 'outbound'
        else:
            journey.direction = 'inbound'
        journey.code = item['journeyId']
        journey.data = item

        try:
            journey.service = Service.objects.get(operator__in=self.operators, line_name__iexact=journey.route_name,
                                                  current=True)
        except (Service.DoesNotExist, Service.MultipleObjectsReturned) as e:
            print(journey.route_name, e)

        if journey.service:
            try:
                departure_time = timezone.localtime(journey.datetime)
                journey.trip = Trip.objects.filter(
                    route__service=journey.service,
                    calendar__in=get_calendars(departure_time),
                    start=timedelta(hours=departure_time.hour, minutes=departure_time.minute)
                ).get()
            except (Trip.MultipleObjectsReturned, Trip.DoesNotExist):
                pass

        return journey

    def create_vehicle_location(self, item):
        heading = item['live']['bearing']
        return VehicleLocation(
            latlong=Point(item['live']['lon'], item['live']['lat']),
            heading=heading
        )
