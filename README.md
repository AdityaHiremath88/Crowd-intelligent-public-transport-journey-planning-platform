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

### Detailed proposal

**Problem and goal.** Delhi bus riders need to compare travel time with likely comfort. A fast journey can involve a crowded stretch, while a later departure may offer a better ride. Yuktix addresses the Phase 1 bus-only challenge by combining static GTFS journey planning with historical ticket evidence. The main proposed contribution is a crowding estimate by route, direction, stop-to-stop segment and time of day, with its uncertainty visible to commuters and operators.

**What is working now.** The public source provides scheduled GTFS journey search, route alternatives, estimated fares where geometry supports them, historical ticket activity by route and hour, and voluntary crowd reports as a separate signal. The existing Android APK demonstrates the offline prototype. The current public implementation **does not yet reconstruct and validate passenger load for each journey segment**. Historical ticket activity must not be displayed as measured onboard occupancy or live crowding.

#### Data and its role

| Input | Intended use | Evidence boundary |
| --- | --- | --- |
| October 2026 ETM and e-ticket records | Use passenger counts, boarding time, route, recorded stops and vehicle number where present to estimate historical demand. | Ticket sales do not directly measure everyone on a bus; some riders and vehicle identifiers are missing. |
| Static Delhi bus GTFS | Identify stops, directions, stop order and scheduled trips; find and time journey options. | A timetable does not prove that a bus ran or arrived on time. |
| Verified bus capacities, if obtained | Translate estimated load into understandable comfort levels. | Without capacity by bus type, exact occupancy percentages and seat claims are not justified. |
| Voluntary crowd reports | Provide separately labelled recent observations in a hosted version. | Reports are self-reported and cannot silently replace historical estimates. |

The repository contains code and synthetic tests, not the supplied raw datasets. Anyone rerunning the proposed analysis needs authorized access to the ticket and GTFS inputs. The [technical note](docs/crowd-estimation-feasibility.md) describes what the present code actually computes.

#### Proposed crowding pipeline

1. **Clean and audit tickets.** Parse timestamps in India Standard Time; normalize route, direction and stop names; preserve passenger counts; record missing and inconsistent fields. Measure how many records survive each rule. Do not treat a generated ID as evidence that two tickets belong to different runs.
2. **Match ticket stops to GTFS.** Match boarding and intended alighting names against stops on the stated route and direction, using aliases and stop order to resolve ambiguity. Flag unmatched, reversed and uncertain pairs instead of forcing a confident match.
3. **Infer bus runs.** Group compatible records using vehicle number, route, direction, date and plausible trip time. Separate repeated runs of the same vehicle with schedule and stop progression. Where a run cannot be distinguished, retain only a coarser route/time estimate and mark its uncertainty.
4. **Estimate load on each segment.** For an inferred run, compute `load after stop = load before stop + boarded passengers − alighted passengers`. Carry the result over consecutive GTFS stops. Inspect negative or implausibly high values; retain matched-ticket counts and reconstruction quality for every segment. This is *ticketed passenger load*, before accounting for missing riders.
5. **Build historical profiles.** Aggregate comparable runs by route, direction, adjacent stop pair, day type and time band. Store a central estimate, spread, sample count and coverage. A route-wide ticket count is not a substitute for segment load.
6. **Create commuter labels only when supported.** With adequate samples and trusted capacity information, map load ranges to labels such as seats likely, standing room and crowded. Show that the estimate is historical, the applicable time band, and its confidence. Otherwise show that a crowd estimate is unavailable.
7. **Validate.** Hold out whole weeks and compare predicted profiles with held-out runs. Report matching coverage, load error, sample sizes, weekday/weekend differences and rush-hour patterns. Investigate corridors and hours that contradict known patterns.

#### Journey planner and user outputs

The rider chooses an origin, destination and departure time. GTFS supplies feasible scheduled bus journeys, travel time and changes. Each result should show the crowding profile for the **segments the rider actually travels**, not just a route-wide score. The comparison should make a fastest journey and a more comfortable journey easy to identify; it can also show a later scheduled departure if available. Comfort-based ordering must wait until the segment model is validated. Fares remain explicitly estimated where an official fare-stage match cannot be confirmed.

Operators should be able to query recurring high-load corridors by route, direction, segment, day type and time band, alongside sample count and confidence. This can guide investigation of overloaded hours without treating low-coverage estimates as established facts. A rerunnable pipeline, its output schema, and validation results are necessary before claiming this operator view is complete.

#### Limitations and evidence gaps

> **Current evidence boundary:** The public prototype supports scheduled journeys and descriptive historical ticket activity. It does **not** yet provide verified stop-by-stop occupancy, a validated comfort ranking, live bus crowding, or calibrated seat availability. Screens and submission material should not imply these features exist.

- **Missing passengers:** Pass holders and other unticketed riders may be absent. Any uplift factor would be an assumption until independently measured and tested for sensitivity.
- **Ambiguous runs:** Vehicle numbers can be null; one vehicle can complete several trips. Tickets may not identify the exact scheduled trip or its initial passenger load.
- **Uncertain stops and destinations:** Ticket stop names can differ from GTFS. An intended destination is not an observed alighting, and uncertain matches reduce segment coverage.
- **Unknown capacity:** Vehicle sizes and seating vary. Passenger counts alone cannot support precise occupancy percentages or claims that seats are available.
- **Short observation window:** Four to five weeks may show regular weekly patterns but cannot establish seasonal, festival, disruption or monsoon behavior. Sparse route/time bands have wider uncertainty.
- **Schedules versus reality:** Static GTFS does not verify actual arrivals, cancellations or transfer success. Historical profiles are not real-time predictions.
- **Prototype completeness:** The public source currently exposes descriptive route/hour ticket activity rather than the full validated segment pipeline. Held-out-week metrics and a short end-to-end demo video remain to be produced.

#### Submission checklist

| Requirement | Status |
| --- | --- |
| Proposal | Problem, data, proposed method, user outputs and limitations are described above. |
| Working prototype | GTFS journey search and the existing offline Android release are available; validated segment crowding remains planned work. |
| Public source and setup | Code and setup instructions are below; supplied datasets are excluded. |
| Short technical note | [Method, assumptions and evidence limits](docs/crowd-estimation-feasibility.md); add matching rates and validation metrics once measured. |
| Short demo video | Pending; record only the features that are working. |

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
