# Yuktix backend v2: scope and API contract

The v2 package runs alongside the existing service until the rebuilt journey flow is implemented and reviewed. Static schedules and ticket activity are distinct evidence types. Historical ticket activity is never occupancy or live crowding.

## Phase 1 boundaries

Included: static GTFS ingestion and validation, canonical GTFS stop lookup, scheduled bus journey search, route-by-time historical ticket-activity profiles, source/coverage metadata, and operator-readable aggregates.

Excluded for now: authentication, native app, in-app live map, real-time vehicle tracking, and physical crowd categories. GTFS stop coordinates are publisher-listed, not independently field-verified. GTFS times are schedules, not live arrivals.

## Implemented endpoints

### `GET /api/v2/health`

Liveness only. Returns `status`, `service`, and `generated_at`, even if no data has been imported.

### `GET /api/v2/capabilities`

Returns schedule, canonical stop-search, and historical route-activity availability flags, plus explicit `false` values for physical crowd estimates and live vehicle tracking. It remains a successful response when the local database is absent, so clients can show what is and is not ready.

### `GET /api/v2/ready`

Readiness for the imported GTFS schedule. Returns source filename/hash, import time, service-date window, imported row counts, and validation issues. Returns HTTP 503 with a structured error if the database is absent or the import is not usable for scheduled routing.

### `GET /api/v2/stops?q={text}&limit={n}&offset={n}`

Search canonical GTFS stops only. Each result returns `stop_id`, `stop_name`, optional coordinates, and `coordinate_source=gtfs_publisher_unverified`. IDs remain opaque to the client. No ETM stop label is silently treated as a GTFS ID.

### `POST /api/v2/journeys/search`

Request:

```json
{
  "origin_stop_id": "GTFS stop ID",
  "destination_stop_id": "GTFS stop ID",
  "departure_datetime": "ISO-8601 datetime with offset",
  "preference": "fastest | balanced | comfort",
  "max_transfers": 1
}
```

Searches active GTFS service for scheduled bus connections, including bounded transfers and after-midnight GTFS service times. Returns itinerary legs and GTFS trip/route/stop IDs, scheduled times, duration, transfers, wait, and score components. `crowd_data_available=false` and `walking_connections_available=false`. Until validated crowd observations exist, `comfort` cannot mean less crowded; ranking currently uses scheduled time and transfer count only.

Each leg and journey option also includes a `fare_estimate`. When route direction and both stops map to the imported DTC stage list, the response provides separate ordinary and AC adult estimates using an assumed approximately 2 km per stage interval and published fare bands. The 2 km conversion is a Yuktix heuristic, not an official distance supplied by the workbook. Because the bus type is not known, both estimates are returned. These are estimates, not official stage-to-stage fare lookups; unmatched legs are `unavailable`, and a journey total is withheld if any leg is unmatched. Fare bands are sourced from [Delhi Tourism's city bus fare table](https://delhitourism.gov.in/transport/city_bus.html); the route-stage workbook is listed on [DTC Services and Time Table](https://dtc.delhi.gov.in/dtc/services-and-time-table).

### `GET /api/v2/routes/{route_id}/activity?target_date={YYYY-MM-DD}&hour={0..23}`

Returns the full cleaned October 2026 ETM history for a matching route-label candidate, target weekday, and transaction hour before the target date. The response keeps `average_passenger_volume` and `average_transaction_count` separate and includes each comparable date, `comparable_day_count`, source, timestamp basis, route-match qualification, and limitations. `status=available` requires at least 3 comparable dates. These are historical ticket-activity values, not onboard load, crowding, stop arrivals, or live data. An exact GTFS `route_short_name` match is only a candidate, not a reviewed route/direction crosswalk. If history is missing or insufficient, values are null rather than zero.

## Remaining backend additions

The capabilities endpoint is already available. Future backend work includes operator summaries of route/time ticket history that do not imply physical crowd levels, plus reviewed GTFS/DTC stop and route crosswalks and an official stage-to-stage fare table if one becomes available.

## Errors and status behavior

- `400/422`: malformed or out-of-range inputs.
- `404`: unknown GTFS stop or route ID.
- `503`: required imported data is missing, unusable, or the requested journey date is outside the loaded service window.
- A successful response can still say evidence is unavailable or insufficient. Never translate that into zero demand or a crowd category.

## Data and import commands

GTFS import writes only to `YUKTIX_V2_DATABASE_PATH`, defaulting to `datasets/processed/yuktix_v2.duckdb`. The ETM importer adds route/time aggregates from the full cleaned bundle to that same database. The raw ticket and GTFS archives and local DuckDB remain outside Git. The user-provided route-stage workbook is included under `datasets/shareable/` so fare estimates can be reproduced.

```powershell
python -m backend_v2.import_gtfs --zip path/to/delhi_buses_static_gtfs_v1.zip
python -m backend_v2.import_etm --zip datasets/shareable/yuktix-october-delhi-clean-data.zip
```

Import the DTC route-stage workbook:

```powershell
python -m backend_v2.import_fare_stages --xlsx datasets/shareable/dtc-route-fare-stage-master.xlsx
```

The v2 API runs alongside the existing service on port 8001:

```powershell
python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8001
```

The schedule's advertised service-date window is not proof that the feed is current or that a bus is operating in real time. October ticket records use `created_at` as a ticket transaction timestamp, not confirmed boarding time.
