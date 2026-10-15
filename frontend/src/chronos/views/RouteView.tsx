// The screen each address names.

import type { Route } from "../logic/route";
import { BooksView } from "./books/BooksView";
import { CalendarsView } from "./calendars/CalendarsView";
import { GoalsView } from "./goals/GoalsView";
import { IssuesView } from "./issues/IssuesView";
import { MapView } from "./map/MapView";
import { PlotlineView } from "./plotline/PlotlineView";
import { ScenesView } from "./scenes/ScenesView";
import { ThreadsView } from "./threads/ThreadsView";

export function RouteView({ route }: { route: Route }) {
  switch (route.view) {
    case "books":
      return <BooksView />;
    case "calendars":
      return <CalendarsView />;
    case "threads":
      return <ThreadsView />;
    case "scenes":
      return <ScenesView />;
    case "goals":
      return <GoalsView selected={route.goal} />;
    case "issues":
      return <IssuesView />;
    case "map":
      return (
        <MapView
          selection={route.selection}
          connectedFrom={route.connectedFrom}
          focusEvent={route.focusEvent}
        />
      );
    case "plotline":
      return <PlotlineView plotline={route.plotline} focusEvent={route.focusEvent} />;
  }
}
