# Known limitations

- Journey planning requires an authorized GTFS Schedule import. Static timetable times are approximate and are not live arrivals; feed freshness and stop positions require independent verification.
- The repository contains no ticket or schedule dataset. Historical ticket activity is unavailable until an authorized local ETM bundle is imported.
- Ticket transactions do not identify confirmed boarding, actual alighting, all riders, or a reliable bus trip. The current public source branch does not provide calibrated onboard occupancy, seat availability, or live crowd levels.
- Fare values are estimates from route geometry, stop coordinates, or an optional local fare-stage workbook. They may differ from the fare charged, especially when geometry is incomplete or concessions apply.
- Community reports are voluntary and may be inaccurate. They are short-lived and cannot be treated as measured headcounts. Public deployment needs stronger authentication, abuse prevention, and operational monitoring.
- Operator analytics are not access controlled. Do not publish a deployment with private data or treat this prototype as production ready.
- Synthetic tests check software behavior; they do not validate real-world crowd prediction accuracy or timetable reliability.

The [API contract](backend-v2-api-contract.md) describes endpoint behavior, and [data sources](data-sources.md) explains provenance and permission boundaries.
