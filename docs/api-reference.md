# CrowdWise API reference

Base path: `/api/v1`. OpenAPI is generated from FastAPI at `/openapi.json`; Swagger UI is `/docs`. All timestamps are ISO-8601. Date ranges are inclusive. Stop and route label values are opaque source identifiers unless explicitly described as GTFS IDs.

The API has 28 business paths. See the [complete endpoint catalog](api-endpoint-catalog.md) and [frontend handoff](FRONTEND_HANDOFF.md) for all paths and the new community, presence, prediction, and optional realtime contracts.

## System

| Method/path | Behavior |
|---|---|
| `GET /health` | Process health plus ETM and GTFS archive/processed availability. |
| `GET /ready` | 200 when core ETM tables are ready, otherwise 503. |
| `GET /api/v1/system/capabilities` | Feature gates; currently states trip loads, crowd categories and live positions unavailable. |
| `GET /api/v1/system/datasets` | Dataset provenance, hashes, versions, counts and coverage if processed. |
| `GET /api/v1/system/methodology` | Machine-readable methodology and evidence caveats. |

## Stops and historical ticket demand

| Method/path | Parameters/behavior |
|---|---|
| `GET /api/v1/stops` | `q`, `limit` (1–5000), `offset`, `source=auto\|etm\|gtfs`; auto selects GTFS only if usable, otherwise ETM labels. |
| `GET /api/v1/stops/map` | Required `south,west,north,east`, optional `limit` (1–5000); requires valid GTFS coordinates. |
| `GET /api/v1/stops/{stop_id}` | ETM summary or GTFS stop detail. GTFS demand is not joined without reviewed mapping. |
| `GET /api/v1/stops/{stop_id}/demand` | Optional `route`, `day_of_week` (0 Monday–6 Sunday), `transaction_hour` (0–23), `date_from`, `date_to`, `limit` (1–5000), `offset`. Returns recorded ticket-start volume, transaction count, days, and paged observations. |

Example: `GET /api/v1/stops/etm_.../demand?date_from=2026-10-01&date_to=2026-10-31&limit=100`.

Response fields include `prediction_type=historical_ticket_start_volume`, `status=historical`, `timestamp_basis`, `passenger_volume`, `transaction_count`, `days_covered`, `observations_truncated`, `total_observations`, and an explicit descriptive confidence label. Demand does not mean people waiting at the stop.

## Route and analytics

| Method/path | Parameters/behavior |
|---|---|
| `GET /api/v1/routes` | `q`, `limit` (1–500), `offset`; historical source route labels, volume, transaction count and observed start-label count. |
| `GET /api/v1/routes/profile` | Required `route_label`; optional inclusive dates; returns totals plus hourly and weekday profiles. |
| `GET /api/v1/analytics/overview` | ETM coverage and data-quality metadata. |
| `GET /api/v1/analytics/trends` | `granularity=day\|week`, optional inclusive `date_from`, `date_to`. |
| `GET /api/v1/analytics/peak-hours` | `day_type=all\|weekday\|weekend`; passenger volume, transaction count and observed date count. |
| `GET /api/v1/analytics/corridors` | `limit` (1–100), optional inclusive dates; ranks recorded route labels by ticket volume, not onboard crowd. |
| `GET /api/v1/analytics/service-profile` | Optional dates; groups source `is_ac` and `ticket_type_id` fields without claiming their business meaning is verified. |

Example response shape:

```json
{
  "data_source": "October-Delhi ETM CSV",
  "generated_at": "2026-11-17T12:00:00Z",
  "points": [
    {"period": "2026-10-01", "passenger_volume": 123, "transaction_count": 118}
  ]
}
```

Numbers above illustrate the schema only and are not Delhi observations.

## Journey search

`POST /api/v1/journeys/search` requires a loaded quality-approved GTFS feed. Request fields: `origin_stop_id`, `destination_stop_id`, `departure_datetime`, `preference=fastest\|balanced\|comfort`, and `max_transfers` (0–3). Naive datetimes are interpreted in the feed timezone (fallback Asia/Kolkata); offset datetimes are converted to that timezone.

```json
{
  "origin_stop_id": "GTFS_STOP_ID",
  "destination_stop_id": "GTFS_STOP_ID",
  "departure_datetime": "2026-11-17T08:30:00+05:30",
  "preference": "balanced",
  "max_transfers": 1
}
```

Each option includes scheduled legs with route/trip IDs and names, boarding/alighting stop IDs/names, per-leg times and stop sequence, overall scheduled duration, waiting time, transfers, transfer stops, ETA source and explainable ranking components. The response carries `crowd_data_available=false`, `walking_connections_available=false` and a note that comfort cannot optimize crowd exposure. No example journey result is supplied because no actual GTFS feed is loaded.

## Errors

- 422: invalid query/body, reversed dates, invalid bounds, or same origin/destination.
- 404: unknown stop or route label.
- 409: GTFS stop demand requested without a reviewed ETM mapping.
- 503: ETM aggregates, GTFS schedule, or required data unavailable.
- 503 `GTFS_SERVICE_DATE_OUT_OF_RANGE`: requested local journey date falls outside the loaded GTFS calendar window; the response includes the feed window.

FastAPI errors use the `{"detail": ...}` envelope; some unavailable cases contain structured codes. Community report submission, recent reports, community category aggregation, opt-in presence signals, historical ticket-activity baseline, realtime feed health, and live vehicle endpoints are now registered. Their semantics and gates are documented in the [endpoint catalog](api-endpoint-catalog.md). These features do not establish measured passenger occupancy. Journey crowd exposure and validated per-stop ETA remain unavailable.
