# API endpoint catalog

**Contract source:** FastAPI `app.main:app`, Pydantic schemas in `app/schemas.py`; current contract has 28 business paths. `/docs` and `/openapi.json` are FastAPI-generated documentation endpoints and are not counted among these paths. Examples below are schema examples, not live results unless explicitly described. ETM outputs are historical. No endpoint currently returns measured physical occupancy.

## Shared behavior

- JSON; dates are ISO `YYYY-MM-DD`; datetimes are ISO-8601. Naive journey datetimes are interpreted in the loaded GTFS timezone (fallback `Asia/Kolkata`).
- Pydantic response models constrain output. Standard request/parameter validation is HTTP 422. Missing ETM or unavailable aggregates generally return 503. Entity lookups return 404; an ETM/GTFS stop without reviewed correspondence returns 409.
- Source tables: processed local October ETM DuckDB; journey/stops optionally use an imported quality-approved GTFS static feed. Route/stop labels from ETM are not reviewed canonical IDs.
- For an error, FastAPI returns `{"detail": "..."}` or a structured `detail` object. An absent crowd result is unavailable, never zero.

## Endpoint inventory

### 1. `GET /health`

Purpose: process liveness and presence of ETM/GTFS artifacts. Request: no parameters. Success response: `HealthResponse` (`status`, `processed_data_available`, `gtfs_available`, `gtfs_processed_available`, `generated_at`). Example: `{"status":"ok","processed_data_available":true,"gtfs_available":false,"gtfs_processed_available":false,"generated_at":"<UTC timestamp>"}`. Errors: normally none for absent data (presence flags are false). Source: local filesystem/DuckDB. Status: operational/liveness, not a crowd estimate.

### 2. `GET /ready`

Purpose: ETM readiness. Request: none. Success `ReadinessResponse`: `{"status":"ready","processed_data_available":true,"generated_at":"<UTC timestamp>"}`. Errors: 503 `{"detail":"Processed ETM database is unavailable"}`. Source: required ETM table presence. Status: readiness only, historical data.

### 3. `GET /api/v1/analytics/overview`

Purpose: row counts, time bounds and data-quality summary. Request: none. Response `OverviewResponse`: dataset/retained/excluded rows, dates, route/vehicle/start/end cardinalities, null/invalid/duplicate counts, passenger volume/mean, `data_source`, `data_status=historical`, `prediction_type=data_quality_overview`, `occupancy_predictions=unavailable`, caveat. Example shape: `{"dataset_rows":2559899,"retained_rows":2559899,"excluded_rows":0,"distinct_routes":2259,"null_vehicle_rows":1242167,"passenger_volume_total":2753606,"data_status":"historical","occupancy_predictions":"unavailable",...}`. These values describe the currently processed local snapshot and may change on reprocessing. Errors: 503 if DB or quality summary missing. Source: October ETM quality table. Historical descriptive data.

### 4. `GET /api/v1/analytics/trends`

Purpose: daily or weekly ticket aggregates. Query: `granularity=day|week` (default day), optional `date_from`, `date_to`. Example request: `/api/v1/analytics/trends?granularity=day&date_from=2026-10-01&date_to=2026-10-31`. Response: `AnalyticsSeriesResponse` with source, `data_status=historical`, `measure=recorded_ticket_volume`, transaction-time basis, generated timestamp and points `{period, passenger_volume, transaction_count}`. Example: `{"points":[{"period":"2026-10-01","passenger_volume":...,"transaction_count":...}],"measure":"recorded_ticket_volume",...}`. Errors: 422 when from > to or invalid enum/date. Source: materialized `daily_demand`. Historical ticket volume, not boardings at verified time.

### 5. `GET /api/v1/analytics/peak-hours`

Purpose: aggregate transaction-time hours for all, weekdays, weekends. Query `day_type=all|weekday|weekend`, default all. Request `/api/v1/analytics/peak-hours?day_type=weekday`. Response `PeakHoursResponse` with `hours[{transaction_hour, passenger_volume, transaction_count, observed_dates}]`, data source/status/time basis. Example shape: `{"day_type":"weekday","hours":[{"transaction_hour":8,"passenger_volume":...,"transaction_count":...,"observed_dates":...}],...}`. Errors: 422 invalid enum. Source: `hourly_demand`. Historical transaction-time distribution; not bus arrival or queue peaks.

### 6. `GET /api/v1/analytics/corridors`

Purpose: top source route-label activity, optionally date-filtered. Query `limit` 1–100 (default20), optional `date_from`, `date_to`. Example `/api/v1/analytics/corridors?limit=10`. Response `CorridorResponse`: routes `{route, passenger_volume, transaction_count, stop_labels}`, source/status/measure/time. Example shape: `{"routes":[{"route":"<source route label>","passenger_volume":...,"transaction_count":...,"stop_labels":...}],...}`. Errors: 422 invalid bounds/limit. Source: `route_demand` and route-start-label catalog. Historical route-label summary; route label/direction not authoritative.

### 7. `GET /api/v1/analytics/service-profile`

Purpose: compare records by raw `is_ac` and `ticket_type_id`. Query optional date range. Example `/api/v1/analytics/service-profile?date_from=2026-10-01`. Response `ServiceProfileResponse`, groups `{is_ac,ticket_type_id,passenger_volume,transaction_count,observed_dates}`, and semantic caveat. Example shape: `{"groups":[{"is_ac":true,"ticket_type_id":1,"passenger_volume":...,"transaction_count":...,"observed_dates":31}],...}`. Errors: 422 date range, 503 aggregate missing. Source: ETM columns. Historical; field meanings and coverage are unverified; not fleet share or occupancy.

### 8. `POST /api/v1/journeys/search`

Purpose: search a loaded validated GTFS static timetable. JSON request `JourneySearchRequest`: `{origin_stop_id:string,destination_stop_id:string,departure_datetime:datetime,preference:fastest|balanced|comfort="balanced",max_transfers:int 0..3=1}`. Example body: `{"origin_stop_id":"<GTFS stop ID>","destination_stop_id":"<GTFS stop ID>","departure_datetime":"2026-11-20T08:00:00+05:30","preference":"balanced","max_transfers":1}`. Response `JourneySearchResponse`: `options` containing legs, ordered stops, scheduled departure/arrival/duration/wait/transfers/score; source/status, `crowd_data_available=false`, `crowd_status=unavailable`, `walking_connections_available=false`, ranking note/message. Successful shape only: `{"options":[],"origin_stop_id":"<id>","destination_stop_id":"<id>","data_status":"scheduled","crowd_data_available":false,...}`. An empty option list means no feasible scheduled journey, not an invitation to invent one. Errors: 422 equal origin/destination or invalid schema; 404 unknown GTFS stops; 503 `GTFS_UNAVAILABLE`, DB missing, or service date outside feed coverage. Source: imported GTFS static feed, if authorized/usable; none currently loaded. Schedule-derived only, not live; crowd optimization currently unavailable and score transparently renormalizes time/transfer preferences.

### 9. `GET /api/v1/routes`

Purpose: paginated route-label catalog ranked by ticket passenger volume, optional substring `q`, `limit` 1–500 (default50), `offset` ≥0. Request `/api/v1/routes?q=123&limit=20&offset=0`. Response `RouteListResponse`: source, historical status, measurement, `items[{route_label,passenger_volume,transaction_count,start_label_count,first_observed_date,last_observed_date}]`, limit/offset/next_offset. Example shape: `{"items":[{"route_label":"<ETM label>","passenger_volume":...,"transaction_count":...,"start_label_count":...}],"limit":20,"offset":0,"next_offset":20,...}`. Errors 422 invalid bounds/length; 503 missing ETM aggregates. Source: October ETM. Historical label profile, not canonical GTFS service list.

### 10. `GET /api/v1/routes/profile`

Purpose: hourly and weekday profile for one exact ETM route label. Required query `route_label`; optional dates. Example `/api/v1/routes/profile?route_label=<URL-encoded-label>&date_from=2026-10-01`. Response `RouteProfileResponse`: totals, dates, start labels, `time_basis`, hourly profile `{transaction_hour,passenger_volume,transaction_count,observed_dates}`, weekday profile `{day_of_week,...}`. Example shape: `{"route_label":"<ETM label>","hourly_profile":[],"weekday_profile":[],"time_basis":"created_at transaction time",...}`. Errors: 422 invalid dates; 404 route label not found; 503 required aggregates absent. Source: October ETM. Historical; direction semantics unverified.

### 11. `GET /api/v1/stops`

Purpose: search/list stop records. Query `q` optional (min length1), `limit` 1–5000 (default50), `offset` ≥0, `source=auto|gtfs|etm` (default auto). Example `/api/v1/stops?q=Kashmere&source=etm&limit=20`. Response `StopListResponse`: items `{id,stop_name,coordinates,demand_available}`, source, total_returned, offset, next_offset. Example shape: `{"items":[{"id":"etm_<stable hash>","stop_name":"<source label>","coordinates":null,"demand_available":true}],"source":"ETM ticket start stop labels; not yet matched to GTFS stop IDs",...}`. Errors: 422 invalid query/limit; 503 no processed data or requested GTFS source unavailable. Source: ETM catalog by default, GTFS only if usable. Historical label or reference catalog; no crosswalk implied.

### 12. `GET /api/v1/stops/map`

Purpose: GTFS stops in geographic bounding box. Required `south,west,north,east`; limit 1–5000 default2000. Example `/api/v1/stops/map?south=28.5&west=77.0&north=28.9&east=77.4&limit=500`. Response `StopMapResponse`: GTFS stop items with coordinates, source, count, next offset. Example shape: `{"items":[{"id":"<GTFS stop ID>","stop_name":"<GTFS name>","coordinates":{"latitude":28.6,"longitude":77.2},"demand_available":false}],...}`. Errors: 422 invalid coordinate/order/limit; 503 no usable validated GTFS. Source: GTFS coordinates. No ETM linkage implied.

### 13. `GET /api/v1/stops/{stop_id}/demand`

Purpose: historical ETM ticket-start activity for one ETM catalog ID. Query filters `route`, `day_of_week` 0–6, `transaction_hour` 0–23, `date_from`, `date_to`; `limit` 1–5000 default5000; `offset` ≥0. Example `/api/v1/stops/etm_<hash>/demand?day_of_week=1&transaction_hour=8&limit=100`. Response `StopDemandResponse`: stop ID/name, passenger volume, transaction count, `prediction_type=historical_ticket_start_volume`, status/source/time basis, days/observation coverage, truncation/pagination, confidence=`descriptive_observation`, note and observations `{date,route,day_of_week,transaction_hour,passenger_volume,transaction_count}`. Example shape: `{"prediction_type":"historical_ticket_start_volume","status":"historical","confidence":"descriptive_observation","observations":[],...}`. Errors: 422 filter/date bounds; 404 unknown ID; 409 GTFS stop exists but no reviewed ETM map; 503 data unavailable. Source: October ETM. Not queue size, actual boarding time or onboard load.

### 14. `GET /api/v1/stops/{stop_id}`

Purpose: ETM stop-label summary or GTFS stop detail. No query. Example `/api/v1/stops/etm_<hash>`. Response `StopDetailResponse`: id/name/optional coordinates, data source/status, observed dates, ticket volume, transaction count, route count. Example shape: `{"id":"etm_<hash>","coordinates":null,"data_status":"historical","passenger_volume":...,"transaction_count":...,"routes_observed":...}`. Errors: 404 unknown stop; 503 DB unavailable. Source: ETM if ID is `etm_...`; otherwise imported GTFS. GTFS-only entries have no demand match and zero counts; this must not be read as observed zero demand.

### 15. `GET /api/v1/system/capabilities`

Purpose: feature/data availability flags. Request none. Response `SystemCapabilitiesResponse`: timestamp, historical analytics, GTFS stop/map/journey flags, trip-level load, crowd classification, live position flags and explanations. Example current shape: `{"historical_ticket_analytics":true,"gtfs_stop_catalog":false,"scheduled_journey_search":false,"trip_level_load_estimation":false,"crowd_classification":false,"live_vehicle_positions":false,"explanation":[...],...}`. Errors: database absence is represented in false capabilities. Source: local database and quality metadata. Data status is a capability report, not a prediction.

### 16. `GET /api/v1/system/datasets`

Purpose: processed dataset provenance catalog. Request none. Response `DatasetCatalogResponse` with entries `{dataset_name,status,source_file,source_sha256,source_size_bytes,generated_at,schema_version,pipeline_version,input_rows,retained_rows,excluded_rows,first_observed,last_observed}`. Example current shape: `{"datasets":[{"dataset_name":"etm","status":"processed","source_sha256":"<hash>","input_rows":2559899,...}],...}`. Errors: missing DB returns an empty list. Source: local DuckDB quality metadata. Historical processing metadata; the report does not imply GTFS is current beyond its recorded range.

### 17. `GET /api/v1/system/methodology`

Purpose: machine-readable methodology summaries for demand, segment loads, crowd classes, routing and confidence. Request none. Response `MethodologyResponse` with five explanatory strings and generated timestamp. Example shape: `{"historical_demand":"Historical ticket activity grouped ...","segment_load":"Unavailable ...","crowd_categories":"Unavailable ...","journey_routing":"...","confidence":"...","generated_at":"<UTC timestamp>"}`. Errors: none expected. Source: versioned backend implementation text. Status: explanatory metadata; not a prediction.

## Contract notes for consumers

1. Discover availability through `/api/v1/system/capabilities` and `/api/v1/system/datasets` before enabling optional experiences.
2. Do not join ETM `etm_...` IDs with GTFS IDs. No reviewed crosswalk exists.
3. Do not interpret missing crowd/GTFS coverage as a low value or a negative route result.
4. Treat timetable times as static schedule estimates, not live ETAs.
5. Do not cache service-date availability indefinitely; feed freshness and calendar range govern it.
6. This catalog is checked against source code and OpenAPI, not a third-party frontend integration test. For exact schema details, query `/openapi.json` for the running build.

## Community reports, presence, forecast and realtime paths

### 18. `POST /api/v1/reports/crowd`

Purpose: accept a recent subjective crowd category at a referenced stop. Required JSON: `stop_id`, `category=low|moderate|high|very_high`, timezone-aware `observed_at`; optional `route_id`, `feedback_code=long_wait|bus_arriving|service_disruption|other`. Required header `X-CrowdWise-Client` is an app-generated opaque token 16–128 chars; do not send a person's name/account. Example:

```http
POST /api/v1/reports/crowd
X-CrowdWise-Client: 9de34c15-a28e-4b49-99a5-f174d13b2510
Content-Type: application/json
```

```json
{"stop_id":"etm_c4f6c32160141e49","category":"high","observed_at":"2026-11-17T12:00:00+05:30","feedback_code":"long_wait"}
```

Success: HTTP 201 `CrowdReportResponse` with opaque `report_id`, `stop_id`, `stop_name`, submitted category, event/created/expiry timestamps, `status=COMMUNITY_REPORTED`, `observation_type=subjective_category_not_headcount`, and stop identity quality. These are schema examples, not real submitted commuter observations. Errors: 422 missing/invalid client header, body/category, timestamp without offset, timestamp >5 minutes future or >10 minutes old, invalid route; 404 unknown stop; 409 same anonymous client already reported at that stop during retention; 429 per-client/per-network quota; 503 store/reference unavailable. Source: voluntary user report. Neither historical nor measured. ETM stop IDs are marked `unreviewed_etm_stop_label` until matched to GTFS.

### 19. `GET /api/v1/reports/stop/{stop_id}`

Purpose: retrieve currently retained individual categories and structured feedback for a stop. Example `/api/v1/reports/stop/etm_c4f6c32160141e49`. Response `CommunityReportsResponse`: `stop_id,status=COMMUNITY_REPORTED|UNAVAILABLE,source=community_reports,report_count,reports[],generated_at,limitations`. Each item has report ID, stop ID/name, optional route, category, feedback code and observation/created/expiry timestamps. Reporter keys, client tokens, IP addresses and precise locations are not returned. Errors: 404 unknown stop, 503 local store/reference unavailable. Reports expire no later than 20 minutes after observation by default. Reporter identity is not verified.

### 20. `GET /api/v1/crowding/stop/{stop_id}`

Purpose: produce a conservative community-reported category aggregate. Example `/api/v1/crowding/stop/etm_c4f6c32160141e49`. Response `CommunityCrowdResponse`: stop, `status`, `observation_type=community_category_aggregate`, nullable `crowd_category`, `report_count`, `agreement_fraction`, `evidence_quality`, `generated_at`, `freshness_seconds`, `limitations`. Category is emitted only with at least 3 retained submissions and at least 60% recency-weighted agreement; each report's weight declines linearly with age to configured expiry. `agreement_fraction` is weighted observed agreement, not model confidence or probability. Client tokens can be rotated, so reports are not proven unique people. Errors: 404 unknown stop, 503 store unavailable. This is community-reported, never physical headcount or onboard occupancy.

### 21. `GET /api/v1/crowding/prediction`

Purpose: historical baseline for represented ticket activity at one ETM start-stop label. Query: required `stop_id`, `target_date` as ISO date, `hour` 0–23. Example `/api/v1/crowding/prediction?stop_id=etm_c4f6c32160141e49&target_date=2026-11-20&hour=8`. Response `TicketActivityForecastResponse`: target, status `PREDICTED|STALE|UNAVAILABLE`, `prediction_type=ticket_transaction_activity_proxy`, predicted represented passenger ticket volume and transaction count (nullable), comparable day count, historical sample min/max, historical max date, method, source, evidence quality and limitations. Forecast is withheld if source is older than 14 days or fewer than 3 prior comparable weekday/hour observations exist; horizon is 14 days. Current October 2026 source is stale as of November 2026, so current calls return `STALE` with null predicted values. Errors: 404 unknown ETM stop, 422 past/out-of-horizon dates/hour, 503 database or quality metadata unavailable. This predicts ticket-record activity only, never waiting people or occupancy.

### 22. `POST /api/v1/presence/signals`

Purpose: one-time, opt-in near-stop signal for participating app clients. Required header `X-CrowdWise-Client`; JSON `stop_id`, `consent=true`, `latitude`, `longitude`, `accuracy_meters`. Example:

```http
POST /api/v1/presence/signals
X-CrowdWise-Client: 9de34c15-a28e-4b49-99a5-f174d13b2510
Content-Type: application/json
```

```json
{"stop_id":"<GTFS stop ID>","consent":true,"latitude":28.61,"longitude":77.21,"accuracy_meters":20}
```

Success 201 `PresenceSignalResponse`: pseudonymous signal ID, stop ID, created/expiry time, `status=ACCEPTED`, and note that exact coordinates were used only for geofence validation and not stored. Requires a quality-usable GTFS stop with coordinates; currently returns 503 without that feed. It validates configured radius (default 100 m) plus reported accuracy; accuracy coarser than radius is rejected. Errors: 422 invalid consent/coordinates/accuracy/outside geofence; 404 unknown stop; 409 duplicate client/stop signal; 429 rate limit; 503 no validated geocoded GTFS or store. A signal is not a person count, queue estimate or background location stream.

### 23. `GET /api/v1/presence/stops/{stop_id}`

Purpose: return the active short-lived signal aggregate. Example `/api/v1/presence/stops/<GTFS stop ID>`. Response `PresenceAggregateResponse`: `status=COMMUNITY_REPORTED|UNAVAILABLE`, `signal_count`, `measure=active_opt_in_participating_signals`, generated timestamp, expiry duration and limitations. Default signal expiry is 10 minutes. Errors: 404 unknown stop; 503 store/reference unavailable. It counts active pseudonymous tokens, not verified unique commuters, total people, or waiting passengers.

### 24. `GET /api/v1/realtime/status`

Purpose: report GTFS-RT adapter configuration, last poll/ingestion, feed timestamp, current/stale record counts, and non-secret error code. Response `RealtimeStatusResponse`: status `HEALTHY|STALE|UNAVAILABLE|ERROR`, `configured`, `authorized`, timestamps and counts. With no configured endpoint, current response is `UNAVAILABLE`, `configured=false`, `authorized=false`, count 0. The API never includes the URL key or authorization header. No network access occurs without `CROWDWISE_GTFS_RT_URL`.

### 25. `GET /api/v1/vehicles/live`

Purpose: list fresh, validated GTFS-RT VehiclePositions. Response `VehicleListResponse`: status, generated and last-success timestamps, vehicles array. Each item contains `vehicle_id`, optional matched trip/route/stop, lat/lon, optional bearing/speed/status, position/feed timestamps, freshness seconds, `status=LIVE_OBSERVED`, and source attribution. With no authorized feed/current static GTFS, returns HTTP 200 with `status=UNAVAILABLE` and an empty array. Invalid/stale positions are not returned as live. Publication still depends on upstream terms.

### 26. `GET /api/v1/vehicles/{vehicle_id}`

Purpose: retrieve one fresh validated vehicle position. Example `/api/v1/vehicles/<upstream vehicle ID>`. Response is `VehiclePositionResponse` (same fields as a list item). Errors: 404 no current vehicle; 503 feed stale/unavailable/error. IDs come only from an authorized feed; never fabricate them.

### 27. `GET /api/v1/vehicles/route/{route_id}`

Purpose: list fresh vehicles matched to a GTFS route ID. Example `/api/v1/vehicles/route/<GTFS route ID>`. Response `VehicleListResponse`. Errors: 404 unknown GTFS route; 503 no validated GTFS reference. An empty healthy response means no matching vehicle positions in that feed snapshot, not zero scheduled service.

### 28. `GET /api/v1/vehicles/{vehicle_id}/eta`

Purpose: explicit ETA boundary. GTFS VehiclePositions alone does not provide a validated stop arrival forecast. With a healthy current vehicle it returns HTTP 503 `ETA_UNAVAILABLE` until an authorized TripUpdates feed or validated travel-time model supports ETA; if feed unavailable returns 503 `REALTIME_UNAVAILABLE`; unknown current vehicle returns 404. No ETA is invented.

## Shared privacy, limits and retention

The API uses HMACs of the opaque client token and network source for duplicate/rate controls; raw client tokens and IPs are not stored. Defaults: 10 submissions per client per rolling hour, 100 per network per rolling hour, report lifetime at most 1,200 seconds after observation, and presence lifetime 600 seconds. Expiry runs on reads/writes and in a 60-second background cleanup loop. A persistent random HMAC key is generated in an ignored sidecar next to the community SQLite file unless `CROWDWISE_REPORT_HMAC_SECRET` is configured. Keep that sidecar and SQLite on a protected persistent volume; do not expose them publicly. Rate limits deter basic abuse but do not prove personhood or replace authentication.
