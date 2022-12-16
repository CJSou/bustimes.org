import xml.etree.cElementTree as ET
from datetime import timedelta
from random import shuffle
from time import sleep

from django.contrib.gis.db.models import Extent, Q
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from bustimes.models import Trip

from ...models import Service, VehicleJourney, VehicleLocation
from ..import_live_vehicles import ImportLiveVehiclesCommand

NS = {
    "a": "http://www.acishorizon.com/",
    "s": "http://www.w3.org/2003/05/soap-envelope",
}

OPERATORS = {"Ulsterbus": "ULB", "Translink Metro": "MET", "Translink Glider": "GDR"}


def items_from_response(response):
    try:
        items = ET.fromstring(response.text)
    except ET.ParseError:
        print(response)
        return ()
    return items.findall(
        "s:Body/a:GetVehiclesNearPointResponse/a:GetVehiclesNearPointResult/a:Vehicles/a:VehicleRealtime",
        NS,
    )


class Command(ImportLiveVehiclesCommand):
    source_name = "acis"
    url = "http://belfastapp.acishorizon.com/DataService.asmx"

    def get_response(self, latitute=None, longitude=None):
        if latitute and longitude:
            latlong = "<latitude>{}</latitude><longitude>{}</longitude>".format(
                latitute, longitude
            )
        else:
            latlong = ""
        data = """
            <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
                <soap12:Body>
                    <GetVehiclesNearPoint xmlns="http://www.acishorizon.com/">
                        {}
                        <maxResults>100</maxResults>
                    </GetVehiclesNearPoint>
                </soap12:Body>
            </soap12:Envelope>
        """.format(
            latlong
        )
        return self.session.post(
            self.url,
            data=data,
            timeout=5,
            headers={"content-type": "application/soap+xml"},
        )

    def get_points(self):
        points = []
        now = self.source.datetime
        services = Service.objects.filter(
            current=True, operator__in=["MET", "GDR", "ULB", "GLE"]
        )
        extent = services.aggregate(Extent("geometry"))["geometry__extent"]
        if extent:
            longitude = extent[0]
            time_since_midnight = timedelta(
                hours=now.hour,
                minutes=now.minute,
                seconds=now.second,
                microseconds=now.microsecond,
            )
            trips = Trip.objects.filter(
                start__lte=time_since_midnight + timedelta(minutes=5),
                end__gte=time_since_midnight - timedelta(minutes=30),
            )
            services = services.filter(route__trip__in=trips)
            while longitude <= extent[2]:
                latitute = extent[1]
                while latitute <= extent[3]:
                    bbox = Polygon.from_bbox(
                        (
                            longitude - 0.05,
                            latitute - 0.05,
                            longitude + 0.05,
                            latitute + 0.05,
                        )
                    )
                    if services.filter(geometry__bboverlaps=bbox).exists():
                        points.append((latitute, longitude))
                    latitute += 0.1
                longitude += 0.1
            shuffle(points)
        return points

    def get_items(self):
        for latitute, longitude in self.get_points():
            self.source.datetime = timezone.now()
            yield from items_from_response(self.get_response(latitute, longitude))
            self.save()
            sleep(1)

    def get_vehicle(self, item):
        operator = item.find("a:VehicleOperatorName", NS).text

        if operator in OPERATORS:
            operator = OPERATORS[operator]
        else:
            operator = "MET"

        vehicle = item.find("a:VehicleId", NS).text

        defaults = {}
        notes = item.find("a:VehicleType", NS)
        if notes is not None:
            defaults["notes"] = notes.text

        defaults["operator_id"] = operator

        vehicle, created = self.vehicles.get_or_create(
            defaults, code=vehicle, source=self.source
        )

        return vehicle, created

    def get_journey(self, item, vehicle):
        journey = VehicleJourney()

        journey.code = item.find("a:VehicleJourneyId", NS).text
        journey.route_name = item.find("a:VehiclePublicServiceCode", NS).text

        latest_journey = vehicle.latest_journey
        if latest_journey:
            if (
                latest_journey.code == journey.code
                and latest_journey.route_name == journey.route_name
            ):
                return latest_journey

        journey.destination = item.find("a:VehicleDestination", NS).text

        operator = item.find("a:VehicleOperatorName", NS).text

        if operator in OPERATORS:
            operator = OPERATORS[operator]
        else:
            operator = "MET"
            print(operator, journey.route_name)

        try:
            try:
                journey.service = Service.objects.get(
                    Q(line_name__iexact=journey.route_name)
                    | Q(line_name__iexact=f"G{journey.route_name}"),
                    operator=operator,
                    current=True,
                )
            except Service.DoesNotExist:
                operator = "GLE"
                journey.service = Service.objects.get(
                    line_name__iexact=journey.route_name,
                    operator=operator,
                    current=True,
                )
        except (Service.MultipleObjectsReturned, Service.DoesNotExist) as e:
            print(e, journey.route_name)

        return journey

    def create_vehicle_location(self, item):
        lat = item.find("a:VehicleLatitude", NS).text
        lon = item.find("a:VehicleLongitude", NS).text
        latlong = Point(float(lon), float(lat))
        return VehicleLocation(
            latlong=latlong,
        )
