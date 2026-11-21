# Yuktix journey-planning handoff

## Product goal and scope

Yuktix is a Delhi bus journey planner. Commuters choose origin, destination, and departure time, then compare schedule-based options. The hackathon brief's central contribution is crowd estimation, but the current evidence supports timetable routing and historical ticket activity only. Do not call ticket activity onboard crowding.

Current scope excludes authentication, native-app work, live vehicle tracking, and an in-app live map. GTFS stop names and coordinates are publisher-listed and have not been independently field-verified. GTFS times are schedules, not live arrivals.

## Current local data

The locally processed DuckDB contains the October 2026 ETM extract and a static GTFS feed. Raw/processed dataset files are private/local and Git-ignored.

The ETM source has 2,559,899 rows across October 1–31, 2026. It has no validated ticket-to-GTFS-trip key. `created_at` is treated as ticket transaction time, not verified boarding time. `ticket_type_id` is a category field, not a unique ticket ID. A generated `synthetic_row_id` only names a row in an export; it does not create a trip relationship.

The static GTFS feed has 2,574 routes, 6,862 stops, 80,357 trips, and 2,737,136 stop-time rows. It has a `block_id` column but all 80,357 values are blank. The feed supports scheduled routing and route segment order, but it does not identify which vehicle operated each trip. A GTFS `trip_id` is not present as a ticket linkage in the ETM rows.

The exact route-label comparison found 1,944 of 2,259 ETM route labels matching GTFS route labels. Treat this as a route-label candidate match, not validation of every ticket's route, direction, stop, or trip.

## Current planner implementation

- Backend journey search: `POST /api/v1/journeys/search`.
- Frontend: mobile-first web prototype under `frontend/`; static frontend development server is `npm run dev`.
- Journey results use the loaded GTFS schedule and explicitly report scheduled/non-live timing, no walking connections, and crowd data unavailable.
- Frontend currently requests at most one transfer. Backend journey search supports a bounded transfer count.
- `GET /api/v1/analytics/route-activity` returns October historical ticket activity for an exact GTFS route label, target weekday, and transaction hour. It requires at least three comparable dates and includes source/time caveats.
- Route activity is displayed separately from “Crowding unknown.” It must not silently affect the comfort ranking.

## Backend v2 rebuild progress

The isolated `backend_v2/` package now contains an independent GTFS importer, canonical stop search, scheduled journey search, and an ETM route-by-time activity importer/query. The current mobile-first frontend journey flow now calls v2 for readiness, origin/destination stop lookup, journey search, and route activity; the remaining older stop/community/operator screens continue to use their existing v1 endpoints during migration.

Import the static feed and the full cleaned ETM bundle before running the rebuilt flow:

```powershell
python -m backend_v2.import_gtfs --zip path/to/delhi_buses_static_gtfs_v1.zip
python -m backend_v2.import_etm --zip datasets/shareable/yuktix-october-delhi-clean-data.zip
python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8002
```

The route activity response groups October records by exact route-label candidate, matching weekday, and transaction hour. It requires at least three earlier comparable days, shows the dates, and leaves route matching explicitly unverified. This is the available historical signal; it is not an onboard crowd estimate and does not yet supply a crowd-optimized route ranking.

## Estimated fare support

The supplied DTC route-stage workbook is imported by `backend_v2.import_fare_stages`. It contains route stop order and fare-stage markers, but no stage-to-stage fare matrix. Journey search therefore returns clearly labeled estimated ordinary and AC adult fares using approximately 2 km per stage interval and published fare bands. These values are planning estimates, not exact DTC tariffs. The response includes confidence and basis notes; it withholds a journey total if any bus leg cannot be matched to the workbook with adequate confidence. Vehicle type, concessions, and any fare exceptions are not inferred.

The initial route/stop name crosswalk is incomplete and has not been manually reviewed. Do not display an unavailable estimate as zero, and do not treat an automated fuzzy name match as a verified stop identity. Expanding fare coverage requires reviewing the route/direction and stop crosswalk against the current operator timetable and tariff.

## Full-data and vehicle-known exports

Two cleaned bundles are checked into `datasets/shareable/` on the contribution branch. They contain derived Parquet files and reports, not the original CSV/ZIP or the local DuckDB database.

- `datasets/shareable/yuktix-october-delhi-clean-data.zip`: all 2,559,899 rows, with route, stop-label, daily, and hourly aggregates. Use this for route/time ticket activity, including rows whose vehicle number is null.
- `datasets/shareable/yuktix-october-delhi-known-vehicle-data.zip`: 1,317,732 rows retained (51.48%); 1,242,167 rows with null vehicle number omitted from this subset. It includes an export-only synthetic row ordinal and vehicle/route/date/hour aggregates. It is useful for exploratory grouping, not trip reconstruction.

The original raw files and local DuckDB remain Git-ignored. The repository's data-source notes document the source and the limits of the available provenance/terms.

The repeatable subset exporter is `scripts/export_vehicle_known_etm.py`. Example:

```powershell
python -m scripts.export_vehicle_known_etm --output-dir work/vehicle-known-export --zip
```

Add `--overwrite` only when intentionally regenerating the named files in that output directory.

## Recommended next journey-planning tasks

1. Confirm GTFS service-date coverage and handle out-of-calendar dates and after-midnight service clearly.
2. Verify journey results for direct routes, transfers, invalid stops, no-path cases, and unavailable data.
3. Improve duplicate-stop disambiguation using GTFS stop/parent-station fields where available; explain that coordinates are publisher-listed.
4. Keep schedule source, generated time, departure/arrival, duration, transfer count, and any walking assumptions visible.
5. Build a route-by-time historical ticket-activity profile using the full ETM dataset. Compare each route to its own history by weekday/weekend and time window, and show observed-day coverage.
6. Chronologically hold out later October dates to evaluate the route/time activity baseline. Do not claim crowd prediction from ticket totals alone.
7. Keep “fastest” and “comfort” ranking honest: until validated crowd data exists, comfort cannot mean less crowded. If a lower-activity option is shown, label it as lower historical ticket activity, not greater comfort.
8. Review and improve the DTC fare-stage to GTFS route/stop crosswalk; replace distance-band estimates with an official stage-to-stage fare matrix if one becomes available.

## Evidence needed for actual crowd categories

To estimate segment load, request a source run/waybill mapping that links service date, vehicle, and operated run to GTFS `trip_id`, plus a reviewed ETM-to-GTFS stop crosswalk and confirmed timestamp semantics. To label “seats available,” “standing room,” or “crowded,” also request vehicle capacity by bus/configuration and independent APC/manual passenger counts for validation. Keep unmatched tickets and abstain where mapping evidence is weak.

## Running locally

From the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

From `frontend/` in another terminal:

```powershell
npm run dev
```

Open `http://localhost:5173`. The local DuckDB is not included in the GitHub clone, so the local datasets and database must be supplied separately for full journey search.

## Git state at handoff

The Yuktix work is on `contribute/yuktix-project-upload`. The current remote branch includes the historical route-activity endpoint and frontend display. The `main` branch has not been modified by this handoff.
