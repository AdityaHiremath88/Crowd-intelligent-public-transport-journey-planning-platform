# CrowdWise backend final status

**Scope:** backend only. Teammate-owned frontend files/folders were not modified.

## Delivered and verified

- Preserved the October 2026 ETM DuckDB pipeline, provenance, source row retention and existing historical analytics.
- Added a separate SQLite store for anonymous community crowd reports and short-lived opt-in presence signals. Records expire automatically; client/network identifiers are HMACed; exact location is not stored; no identity/headcount claim is made.
- Added configurable optional GTFS-Realtime VehiclePositions ingestion with protobuf parsing, HTTPS enforcement, no redirects, timeout, status/error tracking, retry backoff, feed/position freshness checks, vehicle/route/trip/stop validation, duplicate vehicle resolution and non-secret APIs. App startup works with no feed URL or key.
- Added same-stop/route/time historical ticket-activity baseline endpoint with max-age, horizon and minimum-sample abstention gates; added chronological ETM holdout script against a weekday-agnostic baseline.
- Added 11 paths beyond the original 17, for 28 documented OpenAPI paths. Current crowd/live/GTFS outputs are explicitly unavailable or gated.
- Added focused tests and handoff documentation. Added final backend smoke coverage for live route behavior and repeated performance measurements across ETM and auxiliary handlers.

## Data and evidence status

- Actual ETM source: 2,559,899 rows, 2,753,606 represented passengers; 31 dates in Oct 2026; 257,483 exact origin/destination label pairs. There are no confirmed boarding timestamps, actual alightings, stable trip keys, complete vehicle identifiers, physical onboard counts or vehicle capacity joins.
- DTC Nov-2026 timetable PDF is downloaded and hashed but remains a reference PDF, not GTFS, and is not used to make routes. Rights for redistribution were not confirmed.
- OTD/Transport Stack access still requires legitimate authorization; no current feed or real-time positions were downloaded.
- No real occupancy, waiting-queue or crowd-prediction accuracy is claimed.

## Partially implemented / blocked

| Feature | State | Blocker / current behavior |
|---|---|---|
| Current Delhi route planner | Adapter/engine/tests implemented; dataset unavailable | Requires authorized current static GTFS. Journey endpoint returns explicit 503 without it. |
| Live buses | Adapter, poller, parser, health/vehicle APIs implemented; integration unconfigured | Requires authorized GTFS-RT URL/key and validated static GTFS for identity matching. Current status `UNAVAILABLE`. |
| Live ETA | Not calculated | Position feed alone is insufficient; requires GTFS TripUpdates or validated arrival-time model. ETA path returns 503 `ETA_UNAVAILABLE`. |
| Community crowd reports | API/store operational | Reports refer to ETM source labels where no GTFS exists; stop identity quality is returned. Anonymous token is not proof of unique person. |
| Opt-in presence | Contract/service implemented and tested; not operational in current local dataset | Requires GTFS stop coordinates; endpoint returns 503 without validated coordinate source. |
| Ticket-activity forecast | Baseline/backtest implemented; current predictions withheld | October data is older than the 14-day freshness gate; endpoint returns `STALE`, null values. Backtest result is not consistently better than baseline. |
| Occupancy/crowd labels | Correctly unavailable | Requires linked trip/run, verified boarding/alighting/load labels, APC/manual ground truth and vehicle capacity. |
| Docker | Configuration prepared | Docker engine unavailable in environment; build/runtime not verified. |

## Prediction backtest result

`python -m scripts.backtest_ticket_activity` uses the last seven October dates as a chronological holdout. It evaluates 164,400 observed-positive stop/hour cells. Same stop + weekday + hour mean versus same stop + hour baseline:

| Metric | Weekday-hour mean | Same-stop-hour baseline |
|---|---:|---:|
| Represented passenger-volume MAE | 1.478 | 1.450 |
| Represented passenger-volume RMSE | 2.568 | 2.692 |
| Transaction-count MAE | 1.304 | 1.304 |
| Transaction-count RMSE | 2.317 | 2.486 |

The candidate improves RMSE but not passenger-volume MAE; transaction MAE is effectively tied. This is not consistent predictive superiority. The production endpoint labels the method baseline-only and currently abstains due source age. Sample selection excludes stop/hour cells with no recorded source rows; results do not validate queue size, boarding demand, occupancy or generalization beyond the month.

## API integration readiness

All **28 OpenAPI paths** are listed in [API endpoint catalog](api-endpoint-catalog.md), with schemas, examples, status/error behavior, data source and availability. Run the server and inspect `/docs` or `/openapi.json`. Frontend-specific setup, examples, data semantics and unavailable states are in [FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md); concise examples are in [API_QUICK_REFERENCE.md](API_QUICK_REFERENCE.md).

## Verification

Recorded during this completion pass:

- Existing suite before modifications: **43 passed**.
- Expanded suite: **59 passed** in the final expanded run.
- `compileall` and `pip check` passed on the combined validation run (`pip check`: no broken requirements).
- Local Uvicorn startup succeeded without a realtime URL/key. HTTP smoke confirmed historical endpoints (200), absent-feed status (200/UNAVAILABLE), unavailable vehicle/ETA (503), report creation and duplicate rejection (201/409), report retrieval, presence aggregate, stale prediction response and 28-path OpenAPI (200). The temporary smoke report was deleted afterward.
- Repeated 18 Nov 2026: ETM query medians 33.840-79.412 ms; community/presence aggregates 55.324-56.211 ms; realtime status 3.292 ms; stale-forecast gate 35.462 ms. Synthetic journey search median 139.807 ms and synthetic GTFS import 4,919.109 ms. No production SLA is claimed. See [performance report](performance-report.md).

## Run and test

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m scripts.process_etm --csv datasets/etm/raw/October-Delhi.csv --database datasets/processed/crowdwise.duckdb
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m pytest -q
python -m compileall -q app scripts tests
python -m pip check
```

For authorized RT access only, set `CROWDWISE_GTFS_RT_URL`, `CROWDWISE_GTFS_RT_API_KEY`, and the documented auth mode in `.env`/secret management. Keep community SQLite and its `.hmac-key` sidecar on a protected writable persistent volume. Never store credentials in the frontend or commit them.


