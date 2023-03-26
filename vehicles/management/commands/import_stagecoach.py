from datetime import datetime, timezone

from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Exists, OuterRef, Q

from busstops.models import Operator, Service, StopPoint

from ...models import Vehicle, VehicleJourney, VehicleLocation
from ..import_live_vehicles import ImportLiveVehiclesCommand

# "fn" "fleetNumber": "10452",
# "ut" "updateTime": "1599550016135",
# "oc" "operatingCompany": "SDVN",
# "sn" "serviceNumber": "RED",
# "dn" "direction": "INBOUND",
# "sd" "serviceId": "XDARED0.I",
# "so" "shortOpco": "SCD",
# "sr" "serviceDescription": "Honiton Road Park & Ride - Exeter, Paris Street",
# "cd" "cancelled": "False",
# "vc" "vehicleActivityCancellation": "False",
# "la" "latitude": "50.7314606",
# "lo" "longitude": "-3.7003877",
# "hg" "heading": "66",
# "cg" "calculatedHeading": "",
# "dd" "destinationDisplay": "City Centre Paris S",
# "or" "originStopReference": "1100DEC10843",
# "on" "originStopName": "Honiton Road P&R",
# "nr" "nextStopReference": "1100DEC10085",
# "nn" "nextStopName": "Sidwell Street",
# "fr" "finalStopReference": "1100DEC10468",
# "fs" "finalStopName": "Paris Street",
# "ao" "aimedOriginStopDepartureTime": "",
# "eo" "expectedOriginStopDepartureTime": "1599414000000",
# "an" "aimedNextStopArrivalTime": "1599414720000",
# "en" "expectedNextStopArrivalTime": "1599414756000",
# "ax" "aimedNextStopDepartureTime": "1599414720000",
# "ex" "expectedNextStopDepartureTime": "1599414522000",
# "af" "aimedFinalStopArrivalTime": "1599414780000",
# "ef" "expectedFinalStopArrivalTime": "1599414728000",
# "ku" "kmlUrl": "https://tis-kml-stagecoach.s3.amazonaws.com/kml/0017f465-8178-4bfb-bfaa-43a81386120e.kml",
# "td" "tripId": "7127",
# "pr" "previousStopOnRoute": "1100DEC10843",
# "cs" "currentStopOnRoute": "",
# "ns" "nextStopOnRoute": "",
# "jc" "isJourneyCompletedHeuristic": "False",
# "rg" "rag": "A"


def parse_timestamp(timestamp):
    if timestamp:
        return datetime.fromtimestamp(int(timestamp) / 1000, timezone.utc)


def has_stop(stop):
    return Exists(
        StopPoint.objects.filter(service=OuterRef("pk"), locality__stoppoint=stop)
    )


class Command(ImportLiveVehiclesCommand):
    source_name = "Stagecoach"
    operator_ids = {"SCEM": "SCGH", "SCSO": "SCCO"}
    previous_locations = {}

    def do_source(self):
        self.operators = Operator.objects.filter(
            Q(parent="Stagecoach") | Q(noc__in=["SCLK", "MEGA"])
        ).in_bulk()

        return super().do_source()

    @staticmethod
    def get_datetime(item):
        return parse_timestamp(item["ut"])

    def prefetch_vehicles(self, vehicle_codes):
        vehicles = self.vehicles.filter(
            operator__in=self.operators, code__in=vehicle_codes
        )
        self.vehicle_cache = {vehicle.code: vehicle for vehicle in vehicles}

    def get_items(self):
        items = []
        vehicle_codes = []

        # build list of vehicles that have moved
        for item in super().get_items()["services"]:
            key = item["fn"]
            value = (item["ut"],)
            if self.previous_locations.get(key) != value:
                items.append(item)
                vehicle_codes.append(key)
                self.previous_locations[key] = value

        self.prefetch_vehicles(vehicle_codes)

        return items

    def get_vehicle(self, item):
        vehicle_code = item["fn"]

        if vehicle_code in self.vehicle_cache:
            return self.vehicle_cache[vehicle_code], False

        operator_id = self.operator_ids.get(item["oc"], item["oc"])
        if operator_id in self.operators:
            operator = self.operators[operator_id]
        else:
            operator = None

        vehicle = Vehicle.objects.filter(operator=None, code=vehicle_code).first()
        if vehicle:
            return vehicle, False

        vehicle = Vehicle.objects.create(
            operator=operator,
            source=self.source,
            code=vehicle_code,
            fleet_code=vehicle_code,
        )
        return vehicle, True

    def get_journey(self, item, vehicle):
        if item["ao"]:  # aimedOriginStopDepartureTime
            departure_time = parse_timestamp(item["ao"])
        else:
            departure_time = None

        code = item.get("td", "")  # trip id

        latest_journey = vehicle.latest_journey

        if departure_time:
            if (
                latest_journey
                and -60
                < (latest_journey.datetime - departure_time).total_seconds()
                < 60
            ):
                return latest_journey
            try:
                return vehicle.vehiclejourney_set.get(datetime=departure_time)
            except VehicleJourney.DoesNotExist:
                pass
        elif item.get("eo"):  # expectedOriginStopDepartureTime
            departure_time = parse_timestamp(item["eo"])

        journey = VehicleJourney(
            datetime=departure_time,
            destination=item.get("dd", ""),  # destinationDisplay
            route_name=item.get("sn", ""),  # serviceNumber
        )

        if code:
            journey.code = code
        elif (
            not departure_time
            and latest_journey
            and journey.route_name == latest_journey.route_name
            and latest_journey.datetime.date() == self.source.datetime.date()
        ):
            journey = latest_journey

        if not journey.service_id and journey.route_name:
            service = journey.route_name
            alternatives = {
                "PULS": "Pulse",
                "YO-Y": "Yo-Yo",
                "TRIA": "Triangle",
            }
            if service in alternatives:
                service = alternatives[service]

            services = Service.objects.filter(current=True, operator__in=self.operators)

            stop = item.get("or") or item.get("pr") or item.get("nr")

            if stop:
                services = services.filter(has_stop(stop))

            if item.get("fr"):
                services = services.filter(has_stop(item["fr"]))

            journey.service = services.filter(
                Q(route__line_name__iexact=service) | Q(line_name__iexact=service)
            ).first()
            if not journey.service:
                try:
                    journey.service = services.get(
                        service_code__icontains=f"-{service}-"
                    )
                except (Service.DoesNotExist, Service.MultipleObjectsReturned):
                    pass

            if not journey.service:
                print(service, item.get("or"), vehicle.get_absolute_url())

        if departure_time and journey.service and not journey.id:
            journey.trip = journey.get_trip(
                destination_ref=item.get("fr"), departure_time=departure_time
            )

        return journey

    def create_vehicle_location(self, item):
        bearing = item.get("hg")

        aimed = item.get("an") or item.get("ax")
        expected = item.get("en") or item.get("ex")
        if aimed and expected:
            aimed = parse_timestamp(aimed)
            expected = parse_timestamp(expected)
            early = aimed - expected
        else:
            early = None

        return VehicleLocation(
            latlong=GEOSGeometry(f"POINT({item['lo']} {item['la']})"),
            heading=bearing,
            early=early,
        )
