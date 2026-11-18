# CrowdWise backend implementation checklist

## Baseline

- [x] Inspect existing modules, API contracts and available datasets before changes.
- [x] Preserve ETM raw data, processed DuckDB and working backend code.
- [x] Run baseline backend tests: 13 passed.
- [x] Confirm the frontend is owned by teammates; backend work only.
- [x] Investigate the official OTD source and authorized public alternatives.

## Backend delivery

- [x] ETM processing, normalized records, quality summaries and repeatable DuckDB build.
- [x] Historical stop-demand API with filters, coverage and stable ETM stop IDs.
- [x] Historical overview, trends, peak-hour and route-label analytics.
- [x] GTFS archive schema/file validator and DuckDB loader.
- [x] GTFS stop search/map contracts and bounded scheduled routing supporting up to three transfers.
- [x] Service calendar/exception handling, after-midnight times and fallback ranking when crowd is unknown.
- [x] Strengthen end-to-end/API tests, data validation, request logging and unavailable-data error contracts.
- [x] Document stable API contract and integration examples for the frontend team.
- [x] Prepare a backend-only Docker image definition and document the required data mount.
- [x] Final verification: 38 backend tests pass; `compileall` succeeds; `pip check` is clean; live HTTP smoke validates ETM endpoints, the 503 GTFS evidence gates and all 17 OpenAPI paths.

## Data-dependent work

- [ ] Obtain a current, authorized Delhi bus GTFS archive.
- [ ] Run GTFS ingestion and validate identifiers, times, calendars and stop coordinates.
- [ ] Review ETM-to-GTFS stop/route candidate mappings; do not auto-accept fuzzy matches.
- [ ] Infer individual trips only if actual identifiers and time evidence support it.
- [ ] Estimate segment load, confidence and crowd bands only after trip inference is defensible.
- [ ] Validate against independent onboard ground truth before claiming occupancy accuracy.

The uncompleted data-dependent items are blocked by the absence of an authorized, current GTFS archive and independent onboard ground truth. GTFS validation and routing logic are exercised with clearly synthetic fixtures, but no Delhi schedule is represented as loaded or verified. Trip reconstruction and segment-level load estimation are intentionally unavailable for the supplied ETM evidence.

