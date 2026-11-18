# Backend deployment guide

## Local run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m scripts.process_etm --csv datasets/etm/raw/October-Delhi.csv --database datasets/processed/crowdwise.duckdb
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Copy `.env.example` to `.env` and set database paths and exact allowed `CROWDWISE_CORS_ORIGINS`. Current startup does not require external keys. The optional realtime adapter is dormant without `CROWDWISE_GTFS_RT_URL`. With authorized access, configure the URL and key only in environment/secret management, select `header` or `query` auth, use HTTPS, and supply the matching validated static GTFS database. Polling interval, timeout, max staleness and retry backoff are configurable; tokens are never returned by APIs/logs. No Delhi realtime feed was accessed in this project.

Community reports/presence and the optional realtime snapshot use a separate SQLite file at `CROWDWISE_COMMUNITY_DB_PATH`. Keep this file and the adjacent generated `.hmac-key` sidecar on a protected persistent writable volume; they must not be public. Configure a persistent external `CROWDWISE_REPORT_HMAC_SECRET` instead if managing keys through the deployment secret store. Do not mount only the DuckDB directory read-only if it contains the community file; use a dedicated writable community path.

## GTFS processing

Acquire and retain an authorized, current static feed. Place it at `datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip`, then run:

```powershell
python -m scripts.process_gtfs --zip datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip --database datasets/processed/crowdwise.duckdb
```

Review `outputs/gtfs_validation.json` and `/api/v1/system/datasets`. A feed failing routing quality checks must not be represented as usable schedule service. This pipeline does not authorize a feed or verify its legal permission.

## Container preparation

The existing `Dockerfile` runs Uvicorn as non-root and provides an HTTP readiness health check. Example commands, after installing Docker:

```sh
docker build -t crowdwise-backend .
docker run --rm -p 8000:8000 \
  -e CROWDWISE_DATABASE_PATH=/app/datasets/processed/crowdwise.duckdb \
  -v /absolute/path/crowdwise.duckdb:/app/datasets/processed/crowdwise.duckdb:ro \
  -e CROWDWISE_COMMUNITY_DB_PATH=/app/datasets/community/crowdwise_signals.sqlite3 \
  -v /absolute/path/crowdwise-community:/app/datasets/community \
  crowdwise-backend
```

Docker is not installed in the current development environment; image build and container health behavior have not been verified here. Confirm container UID can read the mounted DB and that the selected DuckDB version can open it read-only before deployment. Keep raw archives outside the image. A read-only database mount is recommended for API serving; ETL jobs should run separately against a writable copy and publish a validated artifact atomically.

## Operating checks

- `GET /health`: liveness plus processed data flags.
- `GET /ready`: ETM readiness (503 if core tables are absent).
- `GET /api/v1/system/capabilities`: feature gate including GTFS schedule availability.
- `GET /api/v1/system/datasets`: source hash, versions and data coverage.
- Set CORS origins to explicit frontend origins; wildcard origins are not recommended.
- The community HMAC key file and SQLite store require persistent volume backup/retention controls. Community report retention is 20 minutes by default; opt-in presence retention is 10 minutes; a cleanup task runs every 60 seconds.
- Rate limiting is a basic abuse control (default 10 per client token/hour and 100 per source network/hour). It does not establish a unique person or provide full authentication/WAF protection.
- The backend currently has no user login/authentication layer; protect network access according to the deployment context.
- Back up the DuckDB file and pipeline JSON reports; never expose raw ticket rows as public downloads.
- Static timetable values are scheduled estimates, not live ETAs. Live vehicle endpoint is unavailable until authorized GTFS-RT access and matching static GTFS are configured. Per-stop ETA remains unavailable without TripUpdates/validated model.
