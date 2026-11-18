# CrowdWise backend

CrowdWise is a Delhi bus journey-planning and historical ticket-demand backend. It uses DuckDB for reproducible ETM processing and FastAPI for query APIs. The frontend is owned by teammates; this repository work is backend-only.

## Evidence status

The local October 2026 ETM CSV contains 2,559,899 ticket rows. It supports historical ticket-start and route summaries, with passenger volume and transaction count kept separate. It does **not** establish waiting queues, confirmed boarding times, actual alightings, individual trips, onboard occupancy or live crowding. No authorized static Delhi GTFS feed is currently in the workspace, so journey search and GTFS maps return unavailable. Router behavior is tested on explicitly synthetic feeds only. The backend now supports voluntary short-lived crowd reports and optional one-shot opt-in presence (the latter requires GTFS stop coordinates); neither is a measured headcount.

See [known limitations](docs/known-limitations.md) and [external data catalog](docs/external-data-catalog.md) for source/access status and the evidence boundary.

The 17 Nov 2026 acquisition check obtained and hashed the linked DTC Nov-2026 timetable PDF, but it is not GTFS and has not been converted into routing data. OTD's listed static feed was last updated in 2024, and static download/realtime access requires authorization. No current authorized GTFS, AVL, APC or capacity data is configured. See the [Delhi data acquisition report](docs/delhi-data-acquisition-report.md), [crowd estimation feasibility](docs/crowd-estimation-feasibility.md) and [ground-truth requirements](docs/ground-truth-data-requirements.md).

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
datasets/community/crowdwise_signals.sqlite3  # generated, private, short-lived signal store
datasets/community/crowdwise_signals.sqlite3.hmac-key  # generated persistent privacy/rate-limit key
outputs/etm_data_quality.json
outputs/gtfs_validation.json
```

Rebuild ETM tables and report:

```powershell
python -m scripts.process_etm --csv datasets/etm/raw/October-Delhi.csv --database datasets/processed/crowdwise.duckdb
```

When an authorized feed is available, validate and load it:

```powershell
python -m scripts.process_gtfs --zip datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip --database datasets/processed/crowdwise.duckdb
```

The ETM pipeline hashes the source, records version and row metadata, does not automatically deduplicate, and builds stop, route, service, daily and hourly aggregates. The GTFS importer validates core file relationships and supported optional-file constraints. Review the JSON reports before enabling downstream use.

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

The API has 28 documented paths. See the [API reference](docs/api-reference.md), [complete endpoint catalog](docs/api-endpoint-catalog.md), and [frontend handoff](docs/FRONTEND_HANDOFF.md). Do not treat absent crowd data as zero or comfortable. Crowd reports are subjective and rate-limited; presence signals count opted-in pseudonymous tokens, not people; current ETM forecasting is withheld as stale; live vehicles and journey routes require authorized external feeds.

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
- [Private GitHub sharing, data setup and Windows teammate onboarding](docs/github-sharing-guide.md)
- [Trip reconstruction feasibility](docs/trip-reconstruction-feasibility.md)
- [Real-world validation plan](docs/real-world-validation-plan.md)
- [Ticket activity forecast methodology/backtest](docs/demand-forecast-methodology.md)

The Dockerfile is prepared but image build/runtime was not verified because Docker is not installed in the development environment. Mount the processed database as a read-only volume for serving and run ETL separately; details are in the deployment guide.
