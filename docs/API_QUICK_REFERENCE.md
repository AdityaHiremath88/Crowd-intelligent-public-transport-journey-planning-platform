# CrowdWise API quick reference

Base URL: `http://127.0.0.1:8000`; prefix `/api/v1`. The full schema and examples are in [FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md), [endpoint catalog](api-endpoint-catalog.md), and runtime `/openapi.json`.

## Discover state first

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/system/capabilities
Invoke-RestMethod http://127.0.0.1:8000/api/v1/system/datasets
Invoke-RestMethod http://127.0.0.1:8000/api/v1/realtime/status
```

## Endpoint list

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Process/data liveness. |
| GET | `/ready` | ETM readiness. |
| GET | `/api/v1/system/capabilities` | Feature gates. |
| GET | `/api/v1/system/datasets` | Local data provenance. |
| GET | `/api/v1/system/methodology` | Method summaries and caveats. |
| GET | `/api/v1/analytics/overview` | ETM data-quality overview. |
| GET | `/api/v1/analytics/trends?granularity=day|week` | Date trend. |
| GET | `/api/v1/analytics/peak-hours?day_type=all|weekday|weekend` | Transaction-hour profile. |
| GET | `/api/v1/analytics/corridors?limit=20` | Route-label ticket activity. |
| GET | `/api/v1/analytics/service-profile` | `is_ac`/ticket type source summaries. |
| GET | `/api/v1/stops?q=...&source=auto|etm|gtfs` | Stop catalog search. |
| GET | `/api/v1/stops/{stop_id}` | Stop detail. |
| GET | `/api/v1/stops/{stop_id}/demand` | Historical ticket-start activity. |
| GET | `/api/v1/stops/map?south=...&west=...&north=...&east=...` | GTFS stop map bounds; requires feed. |
| GET | `/api/v1/routes?q=...` | Historical route labels. |
| GET | `/api/v1/routes/profile?route_label=...` | Route label profile. |
| POST | `/api/v1/journeys/search` | GTFS schedule search; requires feed. |
| POST | `/api/v1/reports/crowd` | Submit subjective category report. |
| GET | `/api/v1/reports/stop/{stop_id}` | Recent reports. |
| GET | `/api/v1/crowding/stop/{stop_id}` | Conservative report aggregate. |
| GET | `/api/v1/crowding/prediction?stop_id=...&target_date=YYYY-MM-DD&hour=8` | Ticket-activity baseline; currently stale. |
| POST | `/api/v1/presence/signals` | Consent-based one-shot geofence signal; requires GTFS coordinates. |
| GET | `/api/v1/presence/stops/{stop_id}` | Active participating signal aggregate. |
| GET | `/api/v1/realtime/status` | RT feed/poll health. |
| GET | `/api/v1/vehicles/live` | Current fresh RT positions. |
| GET | `/api/v1/vehicles/{vehicle_id}` | Current vehicle detail. |
| GET | `/api/v1/vehicles/route/{route_id}` | Current route-matched vehicles. |
| GET | `/api/v1/vehicles/{vehicle_id}/eta` | ETA contract; currently unavailable without TripUpdates/model. |

## Copyable calls

Historical stop activity (IDs are opaque ETM labels in current setup):

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/stops?source=etm&q=Saket&limit=10'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/analytics/peak-hours?day_type=weekday'
```

Journey search, when GTFS is enabled:

```powershell
$body = @{
  origin_stop_id = '<GTFS stop ID>'
  destination_stop_id = '<GTFS stop ID>'
  departure_datetime = '2026-11-20T08:00:00+05:30'
  preference = 'balanced'
  max_transfers = 1
} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/journeys/search' -Method Post -ContentType 'application/json' -Body $body
```

Community report (token must be random opaque client-generated value, not user information):

```powershell
$headers = @{ 'X-CrowdWise-Client' = [guid]::NewGuid().ToString() }
$body = @{
  stop_id = '<stop ID from API>'
  category = 'moderate'
  observed_at = (Get-Date).ToUniversalTime().ToString('o')
  feedback_code = 'long_wait'
} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/reports/crowd' -Method Post -ContentType 'application/json' -Headers $headers -Body $body
```

Realtime current state (local configuration currently returns `UNAVAILABLE`):

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/realtime/status'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/vehicles/live'
```

## Status/error handling

New source states: `LIVE_OBSERVED`, `COMMUNITY_REPORTED`, `PREDICTED`, `HISTORICAL_ONLY`, `UNAVAILABLE`, `STALE`, `ERROR`. Existing historical APIs retain their established lower-case `historical` data-status fields. Expected errors: 404 unknown identifier; 409 duplicate/review-missing mapping; 422 invalid request; 429 rate-limited submission; 503 missing data/feed/ETA. Some list endpoints return HTTP 200 with explicit unavailable status and an empty list. Never turn unavailable into zero crowd or comfortable.
