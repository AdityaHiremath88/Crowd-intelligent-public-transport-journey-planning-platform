# Yuktix frontend

Mobile-first, responsive web app for Delhi bus riders. The current runnable frontend is plain HTML, CSS, and JavaScript modules. The older `src/` React files are not loaded by the page and are not part of the build; they are retained so the earlier scaffold is not lost.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

1. Start the rebuilt v2 FastAPI backend from the repository root at `http://localhost:8001` (import GTFS and the cleaned ETM bundle first; see the root README).
2. From this folder, run `npm install` once, then `npm run dev`.
3. Open `http://localhost:5173` (use `localhost`, which is allowed by the backend CORS defaults).

For a phone on the same Wi-Fi, use `npm run dev:network`, set `window.YUKTIX_API_BASE` in `config.example.js` to the development computer's LAN address, and add the frontend origin to `CROWDWISE_CORS_ORIGINS` in the backend environment. Installable PWA behavior requires HTTPS outside localhost. This is an installable web app, not a native Android/iOS package.

The API URL is set centrally in `config.example.js` as `window.YUKTIX_API_BASE`. Change it for another backend origin. Do not put credentials in this public frontend configuration.

## Checks

- `npm run build` checks JavaScript syntax, including the service worker.
- `npm test` runs API-client contract tests using Node's built-in test runner and mocked HTTP responses.
- `npm run lint` runs ESLint.
- `npm run test:e2e` runs the mobile and desktop workflows in Chrome; set `CHROME_PATH` if Chrome is installed in a nonstandard location.
- From the repository root, `.\\.venv\\Scripts\\python.exe -m pytest -q` runs the backend suite after installing `requirements-dev.txt`.

## Connected API paths

- `GET /api/v2/capabilities`
- `GET /api/v2/stops?q=...&limit=...`
- `POST /api/v2/journeys/search`
- `GET /api/v2/routes/{route_id}/activity?target_date=YYYY-MM-DD&hour=0..23`
- `GET /api/v1/stops?q=...&limit=...` for existing stop details and community features
- `GET /api/v1/stops/{stop_id}`
- `GET /api/v1/stops/{stop_id}/demand`
- `GET /api/v1/crowding/stop/{stop_id}`
- `GET /api/v1/reports/stop/{stop_id}`
- `POST /api/v1/reports/crowd`
- `GET /api/v1/analytics/overview`, `/trends`, and `/corridors`

Most requests have a 12-second timeout; the first journey search after a backend restart gets up to 60 seconds to load the saved timetable into memory. Requests return explicit network, timeout, and API errors. Stop autocomplete is debounced and requires a returned stop ID; typing a name alone does not validate it.

## Product data boundaries

- The supplied Yuktix Orbit UI pack informs the visual style for home search, journey comparison/details, reporting, and insights. Demonstration-only route names and live crowd states are replaced by backend results, unavailable states, historical ticket activity, and labeled fare estimates.
- The app does not show a live map or vehicle positions, even if a feed is available.
- Stop search uses the loaded GTFS stop catalog and its publisher-provided coordinates. The UI displays coordinates to help distinguish duplicate stop names and explicitly says they are not field-verified.
- October ticket activity is historical transaction data; it is not people waiting, bus occupancy, a crowd estimate, or a live condition. Journey options show route activity only when the matching weekday/hour has at least three prior observations, and show the dates used.
- Crowd reports are voluntary subjective observations. The UI shows individual reports and backend aggregates under separate community labels.
- Scheduled journey search uses the loaded static GTFS timetable. Times are marked approximate and are not live arrivals. Fare estimates appear only when route and stop matching succeeds, and are labeled estimates. No sample routes, fabricated schedules, or live ETAs are shown.
- Authentication is unavailable because the backend has no account service. The frontend does not collect or pretend to validate credentials.
- Saved journeys are available only for backend-confirmed journeys and remain in this browser; they do not sync.
- Reporting submits a real community report. Do not use the production service for test submissions; use the backend's isolated tests.

## Current implementation limits

This is a working prototype for schedule-based journey planning, stop lookup, historical ticket activity, community reports, and operator analytics. The GTFS snapshot's publisher authorization and currentness have not been independently confirmed; the source describes stop times as rough estimates. Live vehicle positions are intentionally hidden from riders. Admin authentication/authorization is absent, so Operator Insights is historical analytics, not a protected operator console.
