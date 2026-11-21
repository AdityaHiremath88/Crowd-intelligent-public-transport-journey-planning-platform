# Yuktix · Delhi Transit App

Yuktix is a mobile-first Delhi transit application backed by the CrowdWise FastAPI services. The repository includes a responsive installable web app, historical ETM analytics, stop insights, voluntary crowd reporting, and journey planning from a locally saved Delhi GTFS static schedule.

## Run the mobile frontend

Start the backend as described below, then from `frontend/` run:

```powershell
npm install
npm run dev
```

Open `http://localhost:5173` on desktop or a phone on the same network (for a phone, bind the frontend and API to a reachable network interface and allow the app origin in backend CORS). The app can be installed from a supported mobile browser. Set its API origin centrally in `frontend/config.example.js`; that file contains no secrets. Frontend setup, API calls, tests, and limitations are in [frontend README](frontend/README.md).

The interface deliberately hides live vehicle maps. The currently configured vehicle feed, if present, does not provide verified crowd levels or passenger occupancy.

## Evidence status

The local October 2026 ETM CSV contains 2,559,899 ticket rows. It supports historical ticket-start and route summaries, with passenger volume and transaction count kept separate. It does **not** establish waiting queues, confirmed boarding times, actual alightings, individual trips, onboard occupancy or live crowding. A locally saved Delhi static GTFS feed is now loaded for stop lookup and scheduled journey search; its timetable is approximate, not live, and its coordinates have not been independently checked in the field. See the [static GTFS integration record](docs/static-gtfs-integration.md). The backend also supports voluntary short-lived crowd reports and optional one-shot opt-in presence; neither is a measured headcount.

See [known limitations](docs/known-limitations.md) and [external data catalog](docs/external-data-catalog.md) for source/access status and the evidence boundary.

The local GTFS archive was already present in the workspace downloads and is used as a prototype schedule snapshot. Its provenance/permission status and freshness have not been independently confirmed. OTD describes stop times as rough estimates; this app labels results as approximate and does not expose live maps or live ETAs. See the [Delhi data acquisition report](docs/delhi-data-acquisition-report.md), [crowd estimation feasibility](docs/crowd-estimation-feasibility.md) and [ground-truth requirements](docs/ground-truth-data-requirements.md).

## Environment and dependencies

Python 3.11+ is supported. PowerShell commands below use the local `.venv`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Configuration is read from environment variables or `.env` (copy `.env.example`, never commit secrets): `CROWDWISE_DATABASE_PATH`, `CROWDWISE_ETM_CSV`, `CROWDWISE_GTFS_ZIP`, `CROWDWISE_CORS_ORIGINS`, `CROWDWISE_COMMUNITY_DB_PATH`, and optional `CROWDWISE_GTFS_RT_*` settings. The application starts normally when realtime credentials/URL are absent.

## Data layout and processing

Keep raw and processed datasets separate. The real ETM files are private/local and Git-ignored:

```text
datasets/etm/raw/October-Delhi.csv
datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip  # only after authorized acquisition
datasets/processed/crowdwise.duckdb
datasets/shareable/yuktix-october-delhi-clean-data.zip  # cleaned derived Parquet bundle
datasets/shareable/yuktix-october-delhi-known-vehicle-data.zip  # subset for exploratory vehicle grouping
datasets/community/crowdwise_signals.sqlite3  # generated, private, short-lived signal store
datasets/community/crowdwise_signals.sqlite3.hmac-key  # generated persistent privacy/rate-limit key
outputs/etm_data_quality.json
outputs/gtfs_validation.json
```

Rebuild ETM tables and report:

```powershell
python -m scripts.process_etm --csv datasets/etm/raw/October-Delhi.csv --database datasets/processed/crowdwise.duckdb
```

To export the subset whose vehicle number is present (without changing the full processed dataset):

```powershell
python -m scripts.export_vehicle_known_etm --output-dir work/vehicle-known-export --zip
```

The export includes an artificial row ordinal only for referencing rows inside that artifact; it is not a ticket or trip identifier. Use the full ETM dataset for route-by-time activity so rows with missing vehicle numbers are not needlessly discarded. See the [journey-planning handoff](docs/journey-planning-handoff.md).

When an authorized feed is available, validate and load it:

```powershell
python -m scripts.process_gtfs --zip datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip --database datasets/processed/crowdwise.duckdb
```

The ETM pipeline hashes the source, records version and row metadata, does not automatically deduplicate, and builds stop, route, service, daily and hourly aggregates. The GTFS importer validates core file relationships and supported optional-file constraints. Review the JSON reports before enabling downstream use.

The two checked-in files under `datasets/shareable/` are derived data bundles for teammate use. The original raw ticket archive and local DuckDB stay out of Git. Use the full bundle for route/time activity; the vehicle-known subset intentionally drops rows without a vehicle number and must not replace the full data for route-level analysis.

## Backend v2 rebuild

The rebuild is being developed in `backend_v2/` beside the existing service. It uses its own DuckDB database and can run on port 8001 while the current backend remains available on port 8000. The v2 contract, health/readiness, GTFS stop search, scheduled journey search, route-by-time historical ticket-activity API, and estimated fare breakdown are documented in [the v2 API contract](docs/backend-v2-api-contract.md).

Import the local static GTFS feed into the v2 database:

```powershell
python -m backend_v2.import_gtfs --zip path/to/delhi_buses_static_gtfs_v1.zip
```

Import the full cleaned ETM route/time activity bundle into the same v2 database:

```powershell
python -m backend_v2.import_etm --zip datasets/shareable/yuktix-october-delhi-clean-data.zip
```

Import the DTC route-stage workbook for estimated standard-adult fares:

```powershell
python -m backend_v2.import_fare_stages --xlsx datasets/shareable/dtc-route-fare-stage-master.xlsx
```

These are estimates based on a Yuktix heuristic of approximately 2 km per fare-stage interval and the ordinary/AC fare bands published by [Delhi Tourism](https://delhitourism.gov.in/transport/city_bus.html). The workbook is listed by [DTC](https://dtc.delhi.gov.in/dtc/services-and-time-table), but does not include stage-to-stage prices or interval distances. The backend withholds estimates when route or stop matching is not confident; these are not official stage-to-stage fare lookups.

Then start the v2 API:

```powershell
python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8001
```

Run reproducible analysis/diagnostics and performance workloads:

```powershell
python -m scripts.analyze_etm_feasibility
python -m scripts.trip_reconstruction_stress_experiment
python -m scripts.benchmark_backend --repetitions 21
```

The trip stress experiment and routing/import benchmarks use labeled synthetic fixtures only; they do not validate real Delhi trip inference, routes or occupancy. Benchmark methods and actual measurements are in [performance report](docs/performance-report.md).

## Run the API

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Swagger/OpenAPI UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Liveness and data status: `GET /health`
- ETM readiness: `GET /ready`
- Capabilities: `GET /api/v1/system/capabilities`

The API has 28 documented paths. See the [API reference](docs/api-reference.md), [complete endpoint catalog](docs/api-endpoint-catalog.md), and [frontend handoff](docs/FRONTEND_HANDOFF.md). Do not treat absent crowd data as zero or comfortable. Crowd reports are subjective and rate-limited; presence signals count opted-in pseudonymous tokens, not people; current ETM forecasting is withheld as stale. Journey routes use the loaded static GTFS snapshot; live vehicles still require authorized realtime access.

For the full endpoint-by-endpoint path, parameters, schema, examples, errors and availability, see [API endpoint catalog](docs/api-endpoint-catalog.md).

Historical ticket-activity backtest (chronological last-seven-day holdout; no occupancy target):

```powershell
python -m scripts.backtest_ticket_activity
```

Optional authorized GTFS-Realtime setup belongs only in server environment configuration. See `.env.example` and the [frontend handoff](docs/FRONTEND_HANDOFF.md); never put the feed key in frontend code.

## Tests and checks

```powershell
python -m pytest -q
python -m compileall -q app scripts tests
python -m pip check
```

Synthetic fixtures validate algorithms and error behavior; they are not mixed into real datasets or API results. Real ETM processing validates counts and descriptive summaries, not occupancy prediction accuracy.

## Architecture and operations

- [Backend architecture](docs/backend-architecture.md)
- [Deployment guide](docs/deployment-guide.md)
- [Performance report](docs/performance-report.md)
- [Testing strategy](docs/testing-strategy.md)
- [Implementation checklist](docs/implementation-checklist.md)
- [All technical docs](docs/)
- [GitHub sharing and local data setup](docs/github-sharing-guide.md)
- [Trip reconstruction feasibility](docs/trip-reconstruction-feasibility.md)
- [Real-world validation plan](docs/real-world-validation-plan.md)
- [Ticket activity forecast methodology/backtest](docs/demand-forecast-methodology.md)

The Dockerfile is prepared but image build/runtime was not verified because Docker is not installed in the development environment. Mount the processed database as a read-only volume for serving and run ETL separately; details are in the deployment guide.
