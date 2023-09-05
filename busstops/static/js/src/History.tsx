import React, { lazy, Suspense } from "react";
import { VehicleJourney } from "./JourneyMap";

const JourneyMap = lazy(() => import("./JourneyMap"));

const apiRoot = process.env.API_ROOT as string;
let hasHistory = 0;

export default function History() {
  const [journeyId, setJourneyId] = React.useState(() => {
    if (window.location.hash.indexOf("#journeys/") === 0) {
      return window.location.hash.slice(1);
    }
  });

  const [loading, setLoading] = React.useState(true);

  const closeMap = React.useCallback(() => {
    if (journeyId) {
      if (hasHistory === 1) {
        window.history.back();
        hasHistory -= 1;
      } else {
        window.location.hash = "";
        hasHistory = 0;
      }
    }
  }, [journeyId]);

  const [journey, setJourney] = React.useState<VehicleJourney>();

  React.useEffect(() => {
    function handleHashChange() {
      if (window.location.hash.indexOf("#journeys/") === 0) {
        setJourneyId(window.location.hash.slice(1));
        hasHistory += 1;
      } else {
        setJourneyId("");
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      // ESC
      if (journeyId && event.key === "Escape") {
        closeMap();
      }
    }

    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [journeyId, closeMap]);

  // let timeout;

  React.useEffect(() => {
    if (journeyId) {
      document.body.classList.add("has-overlay");

      setLoading(true);

      let url = apiRoot;
      if (window.SERVICE_ID) {
        url += "services/" + window.SERVICE_ID + "/";
      } else if (window.VEHICLE_ID) {
        url += "vehicles/" + window.VEHICLE_ID + "/";
      }
      url += journeyId + ".json";

      fetch(url).then((response) => {
        if (response.ok) {
          response.json().then((data) => {
            data.id = journeyId;
            setLoading(false);
            setJourney(data);
          });
        }
      });
    } else {
      document.body.classList.remove("has-overlay");
    }
  }, [journeyId]);

  if (!journeyId) {
    return;
  }

  const closeButton = (
    <button onClick={closeMap} className="map-button">
      Close map
    </button>
  );

  return (
    <React.Fragment>
      <div className="service-map">
        {closeButton}
        <Suspense fallback={<div className="sorry">Loading…</div>}>
          <JourneyMap journey={journey} loading={loading} />
        </Suspense>
      </div>
    </React.Fragment>
  );
}
