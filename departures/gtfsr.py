import requests
from datetime import timedelta
from google.transit import gtfs_realtime_pb2
from django.core.cache import cache
from django.conf import settings
from google.protobuf import json_format
from bustimes.formatting import format_timedelta

url = "https://api.nationaltransport.ie/gtfsr/v1"


def get_response():
    if settings.NTA_API_KEY:
        url = "https://api.nationaltransport.ie/gtfsr/v1"
        response = requests.get(
            url, headers={"x-api-key": settings.NTA_API_KEY}, timeout=10
        )
        cache.set("ntaie", True, 30)
        if response.ok:
            return response.content


def get_feed():
    if not cache.get("ntaie"):
        content = get_response()
        if content:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(content)
            cache.set("ntaie_feed", 300)
            return feed
    return cache.get("ntaie_feed")


def get_trip_update(trip):
    trip_id = trip.ticket_machine_code
    if trip_id:
        feed = get_feed()
        if feed:
            for entity in feed.entity:
                if entity.trip_update.trip.trip_id == trip_id:
                    return json_format.MessageToDict(entity)


def apply_trip_update(stops, trip_update):
    if "stopTimeUpdate" not in trip_update["tripUpdate"]:
        return

    stops_by_sequence = {}
    for stop in stops:
        assert stop.sequence not in stops_by_sequence
        stops_by_sequence[stop.sequence] = stop
        stop.update = None

    for stop_time_update in trip_update["tripUpdate"]["stopTimeUpdate"]:
        sequence = stop_time_update["stopSequence"]
        stop_time = stops_by_sequence[sequence]
        assert sequence == stop_time.sequence
        assert stop_time_update["stopId"] == stop_time.stop_id
        stop_time.update = stop_time_update

    stop_time_update = None
    for stop_time in stops:
        if stop_time.update:
            stop_time_update = stop_time.update

        if stop_time_update:
            stop_time.update = stop_time_update
            if stop_time_update["scheduleRelationship"] == "SKIPPED":
                continue
            if stop_time.arrival and "arrival" in stop_time_update:
                stop_time.expected_arrival = format_timedelta(
                    stop_time.arrival
                    + timedelta(seconds=stop_time_update["arrival"]["delay"])
                )
            if stop_time.departure and "departure" in stop_time_update:
                stop_time.expected_departure = format_timedelta(
                    stop_time.departure
                    + timedelta(seconds=stop_time_update["departure"]["delay"])
                )


def update_stop_departures(departures):
    for departure in departures:
        stop_time = departure["stop_time"]
        trip = stop_time.trip

        trip_update = get_trip_update(trip)
        if trip_update:
            if trip_update["tripUpdate"]["trip"]["scheduleRelationship"] == "CANCELED":
                departure["cancelled"] = True
            else:
                stop_time_update = None
                for update in trip_update["tripUpdate"]["stopTimeUpdate"]:
                    if update["stopSequence"] > stop_time.sequence:
                        break
                    stop_time_update = update
                if stop_time_update:
                    if stop_time_update["scheduleRelationship"] == "SKIPPED":
                        departure["cancelled"] = True
                    elif "departure" in stop_time_update:
                        delay = timedelta(
                            seconds=stop_time_update["departure"]["delay"]
                        )
                        departure["live"] = departure["time"] + delay
