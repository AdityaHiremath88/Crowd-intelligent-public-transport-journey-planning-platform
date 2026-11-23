# Run Yuktix locally

This repository contains source code and synthetic tests. It does not include the Delhi GTFS ZIP, October ticket records, fare workbook, APK, or other redistribution-sensitive artifacts.

1. Install Git, Python 3.12, and Node.js 20 or newer.
2. Clone this repository and create a Python virtual environment. Install `requirements.txt`.
3. Obtain a Delhi bus GTFS Schedule ZIP from an authorized source. Place it under `datasets/gtfs/raw/` and run `python -m backend_v2.import_gtfs --zip <path-to-zip>`.
4. Start the API with `python -m uvicorn backend_v2.main:app --host 127.0.0.1 --port 8002`.
5. In `frontend/`, run `npm ci` and `npm run dev`, then open `http://localhost:5173`.

A GTFS import is required for stop lookup and journey search. The ETM bundle is optional for historical ticket activity. The fare-stage workbook is optional when usable GTFS route geometry or stop coordinates are present. Keep all downloaded and generated data local. `frontend/config.example.js` sets the API origin; never put credentials there.

To verify the code, run `python -m pytest -q` in the repository root after installing `requirements-dev.txt`, then `npm test`, `npm run lint`, and `npm run build` inside `frontend/`. The browser workflow check also needs Chrome: `npm run test:e2e`.

This is a prototype. Scheduled times are not live arrivals; ticket history is not measured occupancy; crowd reports are voluntary observations. See [known limitations](known-limitations.md).
