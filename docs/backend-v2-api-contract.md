# Yuktix backend v2: scope and API contract

This is the new backend contract being developed alongside the existing service. The v2 package uses an isolated DuckDB path and does not replace the current API until the new journey flow is implemented and reviewed. Static schedule data and ticket activity are distinct evidence types; historical ticket activity is never an occupancy or live-crowd value.

## Phase 1 boundaries

Included: static GTFS ingestion and validation, canonical GTFS stop lookup, scheduled bus journey search, route-by-time historical ticket-activity profiles, source/coverage metadata, and operator-readable aggregates.

Excluded for now: authentication, native app, in-app live map, real-time vehicle tracking, and physical crowd categories. GTFS times are scheduled values. GTFS stops/coordinates are publisher-listed and are not field-verified.

## Implemented foundation endpoints

### `GET /api/v2/health`

Liveness only. Returns `status`, `service`, and `generated_at`. It remains successful if no data has been imported.

### `GET /api/v2/ready`

Readiness for the imported GTFS schedule. Returns source filename/hash, import time, service-date window, imported row counts, and validation issues. Returns HTTP 503 with a structured error if the database is absent or the import is not usable for scheduled routing.

## Planned journey and stop endpoints

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

Response includes feasible scheduled options and their legs, route/trip IDs, boarding/alighting stop IDs, scheduled departure/arrival, duration, transfers, wait, source, and generation time. It also includes `crowd_data_available=false`, `walking_connections_available=false`, and a `ranking_note` describing which criteria actually affected ranking. Until validated crowd data exists, `comfort` must not be represented as crowd-optimized.

### `GET /api/v2/routes/{route_id}/activity?date={YYYY-MM-DD}&hour={0..23}`

Returns historical ticket-activity summary for comparable weekday/time observations: separate represented passenger-ticket volume and transaction count, history dates, comparable-day count, metric basis, and limitations. Status is `available`, `insufficient_history`, or `unavailable`; missing observations are not zero. The UI calls this *historical ticket activity*, never crowding.

## Error and data-status behavior

- `400/422`: malformed or out-of-range inputs.
- `404`: unknown GTFS stop or route ID.
- `503`: required imported data is missing, unusable, or the requested date is outside the loaded service window.
- A successful HTTP response may still indicate unavailable evidence. Never translate that into zero demand or a crowd category.

## Data and import commands

The v2 importer writes only to `YUKTIX_V2_DATABASE_PATH`, defaulting to `datasets/processed/yuktix_v2.duckdb`. Raw datasets stay outside Git. Example:

```powershell
python -m backend_v2.import_gtfs --zip path/to/delhi_buses_static_gtfs_v1.zip
```

The v2 API runs alongside the existing service on port 8001:

```powershell
python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8001
```

The service-date window in the import report is the schedule's advertised coverage, not proof that the feed is current or that a bus is operating in real time.
