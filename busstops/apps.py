# import os

# import beeline
from django.apps import AppConfig


class BusTimesConfig(AppConfig):
    name = "busstops"

    # def ready(self):
    #     if os.environ.get("HONEYCOMB_KEY"):
    #         beeline.init(
    #             writekey=os.environ["HONEYCOMB_KEY"],
    #             service_name=os.environ.get("HONEYCOMB_SERVICE_NAME", "bustimes"),
    #             sample_rate=int(os.environ.get("HONEYCOMB_SAMPLE_RATE", 40)),
    #         )
