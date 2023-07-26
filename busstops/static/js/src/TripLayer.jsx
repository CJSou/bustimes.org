import React from "react";

import TripTimetable from "./TripTimetable";

const apiRoot = "https://bustimes.org";

export default function TripLayer({ tripId }) {
  const [trip, setTrip] = React.useState(null);

  React.useEffect(() => {
    fetch(`${apiRoot}/api/trips/${tripId}/`).then((response) => {
      response.json().then(setTrip);
    });
  }, [tripId]);

  if (!trip) {
    return <div className="trip-timetable"><div className="sorry">Loading trip #{tripId}…</div></div>;
  }

  return <TripTimetable trip={ trip } />;
}
