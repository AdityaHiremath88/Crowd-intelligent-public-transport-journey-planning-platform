# Run Yuktix from GitHub on Windows

This guide runs the mobile-friendly Yuktix web app and its local API on a Windows PC. The frontend is a web app; it does not need to be installed as a native Android or iPhone application.

## What is included

- Frontend source, backend source, and the cleaned October ticket-activity bundle are in this repository.
- The DTC route-stage workbook used by the fare estimate is included under `datasets/shareable/`.
- The supplied GTFS schedule ZIP is included at `datasets/shareable/delhi_buses_static_gtfs_v1.zip`. Its provenance and redistribution permission have not been independently confirmed.
- Journey search requires that GTFS archive. Historical route activity and fare-stage estimates also require the included ETM and fare-stage data to be imported into the local database.

## 1. Download the project

Install Git, Python 3.12, and Node.js 20 or later. Then open PowerShell and run:

```powershell
git clone --branch main https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform.git yuktix
cd yuktix
```

## 2. Set up and load the backend data

In the project folder, create a Python environment and install the backend packages:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the included Delhi static GTFS ZIP to the importer input path:

```text
datasets\shareable\delhi_buses_static_gtfs_v1.zip
```

Then import the schedule, the included cleaned October ticket activity, and the included fare-stage workbook:

```powershell
python -m backend_v2.import_gtfs --zip datasets/shareable/delhi_buses_static_gtfs_v1.zip
python -m backend_v2.import_etm --zip datasets/shareable/yuktix-october-delhi-clean-data.zip
python -m backend_v2.import_fare_stages --xlsx datasets/shareable/dtc-route-fare-stage-master.xlsx
```

## 3. Start the backend

Keep this PowerShell window open:

```powershell
python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8002
```

Confirm the API is responding at `http://127.0.0.1:8002/api/v2/health`.

## 4. Start the frontend

Open a second PowerShell window in the project folder:

```powershell
cd yuktix\frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Keep both windows open while using the app. To stop either server, press `Ctrl+C` in its window.

## Notes

- The app expects the backend at `http://127.0.0.1:8002`. To use a hosted or another computer's backend, change `window.YUKTIX_API_BASE` in `frontend/config.example.js` and allow the frontend origin in backend CORS settings.
- A locally reachable backend is required for stop search, route search, journey results, fares, historical activity, and crowd reports. The page itself can load without it, but connected features will not work.
- Schedule times are based on static GTFS and are not live arrivals. October ticket history is historical activity, not measured onboard crowding. Fare values are estimates.
- `datasets/gtfs/raw/`, `datasets/processed/`, and local environment files are intentionally ignored by Git. The shareable GTFS archive is committed under `datasets/shareable/`. Do not add API keys or other secrets to the public frontend or repository.
- For browser UI checks, install Chrome. Run `npm test` and `npm run test:e2e` from `frontend/`; run `python -m pytest -q` from the project root.
