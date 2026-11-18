# CrowdWise frontend

Mobile-first, responsive web app for Delhi bus riders. The current runnable frontend is plain HTML, CSS, and JavaScript modules. The older `src/` React files are not loaded by the page and are not part of the build; they are retained so the earlier scaffold is not lost.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

1. Start the FastAPI backend from the repository root at `http://localhost:8000`.
2. From this folder, run `npm install` once, then `npm run dev`.
3. Open `http://localhost:5173` (use `localhost`, which is allowed by the backend CORS defaults).

For a phone on the same Wi-Fi, use `npm run dev:network`, set `window.CROWDWISE_API_BASE` in `config.example.js` to the development computer's LAN address, and add the frontend origin to `CROWDWISE_CORS_ORIGINS` in the backend environment. Installable PWA behavior requires HTTPS outside localhost. This is an installable web app, not a native Android/iOS package.

The API URL is set centrally in `config.example.js` as `window.CROWDWISE_API_BASE`. Change it for another backend origin. The legacy `window.YUKTIX_API_BASE` alias remains supported for existing installs. Do not put credentials in this public frontend configuration.

## Checks

- `npm run build` checks JavaScript syntax, including the service worker.
- `npm test` runs API-client contract tests using Node's built-in test runner and mocked HTTP responses.
- `npm run lint` runs ESLint.
- `npm run test:e2e` runs the mobile and desktop workflows in Chrome; set `CHROME_PATH` if Chrome is installed in a nonstandard location.
- From the repository root, `.\\.venv\\Scripts\\python.exe -m pytest -q` runs the backend suite after installing `requirements-dev.txt`.

## Connected API paths

- `GET /api/v1/system/capabilities`
- `GET /api/v1/stops?q=...&limit=...`
- `POST /api/v1/stops/nearby` after the user requests current location and grants browser permission
- `GET /api/v1/stops/{stop_id}`
- `GET /api/v1/stops/{stop_id}/demand`
- `GET /api/v1/crowding/stop/{stop_id}`
- `GET /api/v1/reports/stop/{stop_id}`
- `POST /api/v1/reports/crowd`
- `POST /api/v1/journeys/search` only when capabilities enable schedule search
- `GET /api/v1/analytics/overview`, `/trends`, and `/corridors`
- `GET /api/v1/realtime/status` and `/api/v1/vehicles/live`

Most requests have a 12-second timeout; the first journey search after a backend restart gets up to 60 seconds to load the saved timetable into memory. Requests return explicit network, timeout, and API errors. Stop autocomplete is debounced and requires a returned stop ID; typing a name alone does not validate it.

## Product data boundaries

- The live map reads vehicle coordinates only from the CrowdWise backend. It shows GPS observation times and feed status, retains last-known positions as stale after a failed request, and labels unmatched route IDs as provider IDs. Movement, ETAs, and occupancy are not inferred.
- The map uses Leaflet 1.9.4 and OpenStreetMap's standard raster tile server by default. Tiles are best-effort with no service guarantee; production deployments with sustained use should select a suitable tile provider and set matching `CROWDWISE_TILE_URL` and `CROWDWISE_TILE_ATTRIBUTION` in the frontend config. Map tiles are not prefetched or cached for offline use.
- Current location is requested only after the rider presses the location button. Browser permission is required; coordinates are posted once to the nearest-stop endpoint, used in memory for that lookup, and not stored. Without validated GTFS, the endpoint returns an unavailable response and the UI asks the rider to search by name.
- Stop search uses the loaded GTFS stop catalog and its publisher-provided coordinates. The UI displays coordinates to help distinguish duplicate stop names and explicitly says they are not field-verified.
- October ticket activity is historical transaction data; it is not people waiting, bus occupancy, a crowd estimate, or a live condition.
- Crowd reports are voluntary subjective observations. The UI shows individual reports and backend aggregates under separate community labels.
- Scheduled journey search uses the loaded static GTFS timetable. Times are marked approximate and are not live arrivals. No sample routes, fares, fabricated schedules, or live ETAs are shown.
- Authentication is unavailable because the backend has no account service. The frontend does not collect or pretend to validate credentials.
- Saved journeys are available only for backend-confirmed journeys and remain in this browser; they do not sync.
- Reporting submits a real community report. Do not use the production service for test submissions; use the backend's isolated tests.

## Current implementation limits

The branch contains a configurable live feed adapter and rider map, but live positions remain unavailable until the authorized provider key is configured and a real feed is successfully decoded. Static GTFS and ETM source files are not included in Git; this checkout needs authorized local datasets before stop search, nearest-stop lookup, schedules, and historical analytics can return data. Admin authentication/authorization is absent, so Operator Insights is historical analytics, not a protected operator console.


