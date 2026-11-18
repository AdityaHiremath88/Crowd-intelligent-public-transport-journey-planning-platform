# GitHub sharing and local data setup

## Repository contents

This private repository contains the CrowdWise web frontend, FastAPI backend, processing scripts, tests, and project documentation. The current target is `AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform`; its existing `main` history is preserved. Contribute through a topic branch and pull request; do not force-push or replace the default branch history.

## Data and secrets

The GitHub source intentionally excludes `.env`, runtime datasets, processed DuckDB files, community signal stores, and generated analysis outputs. ETM data redistribution rights are not established. The static Delhi GTFS archive is used locally for prototype schedule search but its provenance, authorization, and freshness have not been independently confirmed, so the feed and loaded database are not included in Git. OTD warns that published stop times are approximate; GTFS coordinates are not ground-verified by this project. See [static GTFS integration](static-gtfs-integration.md) and [external data catalog](external-data-catalog.md).

Keep real credentials in local untracked `.env` files or a deployment secret manager. Never place API keys, user data, local database files, raw source archives, or generated reports in GitHub issues, frontend configuration, source files, or `.env.example`. The root `.gitignore` preserves these exclusions; check `git status --ignored` before preparing commits.

The source project does not include `datasets/processed/crowdwise.duckdb`. A new clone must obtain only data authorized for that recipient through the approved private data-transfer channel and place it at the configured database path. Without the local processed database and GTFS archive, historical analytics and scheduled journey search will report unavailable rather than use invented data.

## Clone and run

Clone the repository, install backend dependencies, and start the API:

```powershell
git clone https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform.git
Set-Location Crowd-intelligent-public-transport-journey-planning-platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, run the mobile-first web frontend:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend calls the API at `http://localhost:8000` by default. A clone without separately authorized local data can show the app shell, but server-backed analytics and journey search remain unavailable.
