# Data sources and permissions

This source repository does not redistribute the Delhi GTFS schedule, October ETM tickets, derived ticket bundles, route-stage workbook, or Android packages. Those files were removed from the tracked tree because permission to publish them has not been established and ticket-level exports can expose sensitive trip or vehicle details.

## GTFS Schedule

The application uses stops, routes, trips, stop times, calendar, and optional shapes from a Delhi bus GTFS Schedule ZIP. Obtain the feed through an authorized provider such as the Delhi Transport Stack. Record the provider, download date, service window, and any redistribution terms. A schedule's future calendar dates do not prove that buses currently operate at those times. Stop coordinates have not been field verified.

## October ETM tickets

The project was developed against approximately 2.56 million October 2026 ticket records with route, stop names, timestamp, passenger count, fare, and optional vehicle number. `created_at` is a ticket transaction time, not confirmed boarding time. Destination is a planned stop, not observed alighting. Some passengers are absent from ticket data. Treat any derived activity as historical and uncertain. Store source and cleaned records locally under ignored dataset paths.

## Fare-stage workbook

The optional route-stage workbook was user-supplied. Its redistribution permission has not been confirmed. The backend can estimate adult fare bands from GTFS geometry or stop coordinates, with lower confidence when it uses straight-line distance. Estimates are not official ticket prices.

## Live feed

An optional GTFS Realtime vehicle-position feed may be configured on the backend with a server-side key. This does not provide a numeric bus crowding or Google Busy Areas API, and the commuter UI does not display live vehicle positions.
