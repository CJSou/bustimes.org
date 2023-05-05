from rest_framework import serializers

from busstops.models import Operator, Service, StopPoint
from bustimes.models import Trip
from vehicles.models import Livery, Vehicle, VehicleJourney, VehicleType


class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleType
        fields = ["id", "name", "double_decker", "coach", "electric"]


class VehicleSerializer(serializers.ModelSerializer):
    operator = serializers.SerializerMethodField()
    livery = serializers.SerializerMethodField()
    vehicle_type = VehicleTypeSerializer()

    def get_operator(self, obj):
        if obj.operator_id:
            return {
                "id": obj.operator_id,
                "name": obj.operator.name,
                "parent": obj.operator.parent,
            }

    def get_livery(self, obj):
        if obj.colours or obj.livery_id:
            return {
                "id": obj.livery_id,
                "name": obj.livery_id and str(obj.livery),
                "left": obj.get_livery(),
                "right": obj.get_livery(90),
            }

    class Meta:
        model = Vehicle
        depth = 1
        fields = [
            "id",
            "slug",
            "fleet_number",
            "fleet_code",
            "reg",
            "vehicle_type",
            "livery",
            "branding",
            "operator",
            "garage",
            "name",
            "notes",
            "withdrawn",
        ]


class OperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Operator
        fields = [
            "noc",
            "slug",
            "name",
            "aka",
            "vehicle_mode",
            "region_id",
            "parent",
            "url",
            "twitter",
        ]


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            "id",
            "slug",
            "line_name",
            "description",
            "region_id",
            "mode",
            "operator",
        ]


class StopSerializer(serializers.ModelSerializer):
    long_name = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    icon = serializers.SerializerMethodField()

    def get_long_name(self, obj):
        return obj.get_long_name()

    def get_location(self, obj):
        if obj.latlong:
            return obj.latlong.coords

    def get_icon(self, obj):
        return obj.get_icon()

    class Meta:
        model = StopPoint
        fields = [
            "atco_code",
            "naptan_code",
            "common_name",
            "long_name",
            "location",
            "indicator",
            "icon",
            "bearing",
            "heading",
            "stop_type",
            "bus_stop_type",
            "created_at",
            "modified_at",
            "active",
        ]


class LiverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Livery
        fields = [
            "id",
            "name",
            "left_css",
            "right_css",
            "white_text",
            "text_colour",
            "stroke_colour",
        ]


class TripSerializer(serializers.ModelSerializer):
    service = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    times = serializers.SerializerMethodField()

    def get_service(self, obj):
        return {
            "id": obj.route.service_id,
            "line_name": obj.route.line_name,
            "mode": obj.route.service.mode if obj.route.service else "",
        }

    def get_operator(self, obj):
        if obj.operator:
            return {
                "noc": obj.operator_id,
                "name": obj.operator.name,
                "vehicle_mode": obj.operator.vehicle_mode,
            }

    def get_times(self, obj):
        route_links = {}
        if obj.route.service:
            for link in obj.route.service.routelink_set.all():
                route_links[(link.from_stop_id, link.to_stop_id)] = link
        previous_stop_id = None

        stop_times = getattr(obj, "stops", obj.stoptime_set.all())

        for stop_time in stop_times:
            route_link = route_links.get((previous_stop_id, stop_time.stop_id))
            if stop := stop_time.stop:
                name = stop.get_name_for_timetable()
                bearing = stop.get_heading()
                location = stop.latlong and stop.latlong.coords
                icon = stop.get_icon()
            else:
                name = stop_time.stop_code
                bearing = None
                location = None
                icon = None
            yield {
                "id": stop_time.id,
                "stop": {
                    "atco_code": stop_time.stop_id,
                    "name": name,
                    "location": location,
                    "bearing": bearing,
                    "icon": icon,
                },
                "aimed_arrival_time": stop_time.arrival_time(),
                "aimed_departure_time": stop_time.departure_time(),
                "track": route_link and route_link.geometry.coords,
                "timing_status": stop_time.timing_status,
                "pick_up": stop_time.pick_up,
                "set_down": stop_time.set_down,
            }
            previous_stop_id = stop_time.stop_id

    class Meta:
        model = Trip
        fields = [
            "id",
            "vehicle_journey_code",
            "ticket_machine_code",
            "block",
            "service",
            "operator",
            "times",
        ]


class VehicleJourneySerializer(serializers.ModelSerializer):
    vehicle = serializers.SerializerMethodField()

    def get_vehicle(self, obj):
        if obj.vehicle_id:
            return {
                "id": obj.vehicle_id,
                "slug": obj.vehicle.slug,
                "fleet_code": obj.vehicle.fleet_code,
                "reg": obj.vehicle.reg,
            }

    class Meta:
        model = VehicleJourney
        fields = ["id", "datetime", "vehicle", "trip_id", "route_name", "destination"]
