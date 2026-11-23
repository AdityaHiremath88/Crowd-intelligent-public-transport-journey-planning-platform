# Yuktix

A mobile-friendly Delhi bus journey planner prototype. It searches a locally imported GTFS timetable, estimates fares from available route geometry, and can display historical ticket activity and voluntary crowd reports. It does not provide live bus occupancy or verified seat availability.

## Prototype submission

| Item | Where to find it |
| --- | --- |
| Proposal | The problem, approach, and data summary below |
| Working prototype | [Download Android APK v1.4.1](https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform/releases/download/v1.4.1/Yuktix-Delhi-Transit-Web-Offline-v1.4.1.apk) |
| Source code and setup | [Browse Android Studio source](android/) or [download the complete v1.4.3 source ZIP](https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform/releases/download/v1.4.3-source/Yuktix-Delhi-Transit-v1.4.3-Android-Studio.zip); web and backend setup is below |
| Short technical note | [Crowd estimation method and evidence limits](docs/crowd-estimation-feasibility.md) |
| Demo video | Pending: a short recording of search, route comparison, journey details, and crowd reporting has not been uploaded |

### Proposal summary

**Problem:** Delhi bus riders need to compare journey time with likely crowding, but static schedules alone do not describe onboard conditions.

**Approach:** Use GTFS stops, routes, and trips for scheduled journey options. Process the October ETM records into historical route-and-time activity and show the evidence source next to each result. Voluntary stop reports are a separate, short-lived signal. Do not label ticket activity as measured occupancy or live crowding.

**Data:** Static Delhi bus GTFS and October 2026 ticket data are used locally when access is authorized. The repository publishes code and synthetic tests, not the supplied datasets. Fare values are estimates from available route geometry or stop positions.

### Install the existing Android prototype

Tap [Download Android APK v1.4.1](https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform/releases/download/v1.4.1/Yuktix-Delhi-Transit-Web-Offline-v1.4.1.apk) on your phone. You can also find the file under **Assets** on the [release page](https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform/releases/tag/v1.4.1). Open the downloaded file and allow installation from your browser or Files app if Android prompts you. The APK contains an offline GTFS schedule and aggregate ticket-activity snapshot; its information is historical, not live. Confirm the data provider's redistribution terms before promoting the APK more widely. The source in this repository is maintained separately from that previously built APK.

## Repository map

| Folder | Purpose |
| --- | --- |
| `frontend/` | Responsive web app and browser tests |
| `android/` | Existing v1.4.3 Android Studio source, without the bundled database |
| `backend_v2/` | Current GTFS journey and fare API, data importers |
| `app/` | Shared report storage and legacy API modules used by the current backend |
| `scripts/` | Dataset processing and validation commands |
| `tests/` | Backend tests with synthetic fixtures |
| `docs/` | Data provenance, API contract, limitations, and setup details |
| `datasets/` | Empty local input folders; data is intentionally excluded from Git |

The earlier v1.4.1 APK and the separate v1.4.3 Android Studio source archive are available through GitHub Releases. The two recent local APK versions are not published here. The source archive includes the offline data snapshot; the browsable `android/` folder excludes it.

## Quick start on Windows

Install Python 3.12 and Node.js 20 or newer. Clone the repository, then in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Obtain a Delhi static GTFS ZIP through an authorized source and keep it outside Git, for example in `datasets/gtfs/raw/`. Import it:

```powershell
python -m backend_v2.import_gtfs --zip datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip
python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8002
```

In a second PowerShell window:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. The frontend expects the API at `http://127.0.0.1:8002`; edit `frontend/config.example.js` if your API runs elsewhere. Without an imported GTFS feed, stop search and journey results are unavailable. The app is a web app; this repository does not ship a native APK.

### Optional historical ticket activity

If you have authorization to use the October ETM data, prepare the cleaned bundle locally using the existing pipeline and import it with `python -m backend_v2.import_etm --zip <path-to-clean-bundle>`. The optional route-stage workbook can be imported with `python -m backend_v2.import_fare_stages --xlsx <path-to-workbook>`. Fare estimates can also use GTFS route shapes or stop coordinates without that workbook. Source datasets are not redistributed here. See [setup details](docs/github-setup-guide.md) and [data sources](docs/data-sources.md).

## Checks

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
cd frontend
npm ci
npm test
npm run lint
npm run build
```

Browser workflow tests require Chrome: `npm run test:e2e`.

## Before deploying publicly

- Check the GTFS feed's permission, service dates, stop positions, and timetable quality. Its static times are not live ETAs.
- Keep ticket-level data, vehicle identifiers, local databases, API keys, signing keys, and report stores outside the repository and frontend bundle.
- Reporting and operator views are prototype features without account authentication. Add abuse controls, access control, and operational monitoring before public deployment.
- Historical ticket activity does not measure actual passengers on a bus. Do not present it as live crowding or seats available.

The current code is a prototype, not a production transit service. See the [API contract](docs/backend-v2-api-contract.md) and [known limitations](docs/known-limitations.md).
