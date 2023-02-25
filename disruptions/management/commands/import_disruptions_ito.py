import xml.etree.cElementTree as ET
from datetime import datetime

import requests
from django.core.management.base import BaseCommand

from busstops.models import DataSource

from .import_siri_sx import handle_item


class Command(BaseCommand):
    def fetch(self):
        session = requests.Session()

        url = "https://siri-sx-tfn.itoworld.com"
        requestor_ref = "BusTimes"
        timestamp = (
            f"<RequestTimestamp>{datetime.utcnow().isoformat()}</RequestTimestamp>"
        )

        source = DataSource.objects.get_or_create(name="Ito World")[0]

        situations = []

        response = session.post(
            url,
            data=f"""<?xml version="1.0" encoding="UTF-8"?>
<Siri xmlns="http://www.siri.org.uk/siri" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.0"
xsi:schemaLocation="http://www.siri.org.uk/siri http://www.siri.org.uk/schema/2.0/xsd/siri.xsd">
    <ServiceRequest>
        {timestamp}
        <RequestorRef>{requestor_ref}</RequestorRef>
        <SituationExchangeRequest version="2.0">
            {timestamp}
        </SituationExchangeRequest>
    </ServiceRequest>
</Siri>""",
            headers={"Content-Type": "application/xml"},
            stream=True,
            timeout=10,
        )

        for _, element in ET.iterparse(response.raw):
            if element.tag[:29] == "{http://www.siri.org.uk/siri}":
                element.tag = element.tag[29:]

            if element.tag.endswith("PtSituationElement"):
                situations.append(handle_item(element, source))
                element.clear()

        source.situation_set.filter(current=True).exclude(id__in=situations).update(
            current=False
        )

    def handle(self, *args, **options):
        self.fetch()
