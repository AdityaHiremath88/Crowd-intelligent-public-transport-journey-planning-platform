# Frontend team API integration notes

This document is the backend integration contract for the separately developed frontend. For exact fields and parameters see [API reference](api-reference.md); generated OpenAPI at `/openapi.json` is authoritative when schemas evolve.

## Base URLs and readiness

Local default: `http://127.0.0.1:8000`. Configure `CROWDWISE_CORS_ORIGINS` with the frontend origins. Check `GET /health`, then `GET /api/v1/system/capabilities` before offering features. `GET /ready` indicates whether core ETM aggregates exist; it does not imply that GTFS routing is enabled.

## Current data-supported experiences

- Stop search with `GET /api/v1/stops?q=...&source=auto`. In the current database this returns opaque ETM ticket-start labels, not canonical GTFS stops.
- Historical stop demand with `GET /api/v1/stops/{stop_id}/demand`. Present it as historical ticket activity with transaction-time basis. Keep `passenger_volume` distinct from `transaction_count`.
- Historical overview and chart sources: `/api/v1/analytics/overview`, `/trends`, `/peak-hours`, `/corridors`, `/service-profile`, plus `/api/v1/routes` and `/routes/profile`.
- Dataset provenance and methodology: `/api/v1/system/datasets` and `/methodology`.

No physical stop queue or bus crowd estimate is currently available. Segment crowd, confidence, crowd classification, live positions and passenger reports are not implemented as misleading placeholders; capability flags expose their unavailability.

## GTFS-dependent features

`GET /api/v1/stops?source=gtfs`, `GET /api/v1/stops/map` and `POST /api/v1/journeys/search` require a loaded quality-approved GTFS feed. No such Delhi feed is currently present, so these calls return HTTP 503. Synthetic test schedules must never be displayed as real Delhi results.

When enabled later, journey search accepts GTFS stop IDs, ISO datetime, preference (`fastest`, `balanced`, `comfort`) and maximum transfers (0–3). Options report static scheduled times, not live ETAs. Response explicitly says `crowd_data_available: false` and `walking_connections_available: false`; comfort preference cannot optimize for crowd exposure yet.

## Error and pagination handling

Expected status codes: 422 invalid input/date/bounds; 404 unknown IDs or route labels; 409 GTFS demand with no reviewed ETM mapping; 503 required data unavailable or a journey date outside the loaded GTFS calendar window (`GTFS_SERVICE_DATE_OUT_OF_RANGE`). FastAPI returns an error `detail` that may be a string or structured code/message object. For stop/route/demand pagination, pass `limit` and `offset`, then follow `next_offset` when non-null. Current stop list `total_returned` means page size, not total catalog size.

Never turn a missing field, unavailable capability, empty list or 503 into a zero-valued crowd level. Display source, historical/scheduled status and caveats near the associated values.

## Request example

```json
{
  "origin_stop_id": "GTFS_STOP_ID",
  "destination_stop_id": "GTFS_STOP_ID",
  "departure_datetime": "2026-11-17T08:30:00+05:30",
  "preference": "balanced",
  "max_transfers": 1
}
```

This illustrates request shape only. No journey prediction is being claimed by this example.


