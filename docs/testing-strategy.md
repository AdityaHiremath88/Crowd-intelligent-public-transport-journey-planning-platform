# Testing and validation strategy

## Test layers

1. Unit tests use small, explicitly synthetic ETM/GTFS fixtures to cover parsing, quality rules, calendar exceptions, after-midnight GTFS times, transfers, ranking and crowd evidence gates.
2. Pipeline integration tests verify ETM source hashing, transactional rollback and aggregate reconciliation; GTFS tests load a constructed feed into an isolated temporary DuckDB and verify quality metadata and table relationships.
3. API tests call FastAPI route logic with temporary DuckDB fixtures and assert response shapes, input validation and unavailable-data behavior.
4. Real-data checks process the local October ETM file and reconcile source rows with retained rows and aggregate sums. They are descriptive checks, not prediction ground truth.
5. Performance checks use the actual processed database with bounded output queries; see `performance-report.md` for environment and caveats.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

Latest recorded verification on 17 Nov 2026: **43 passed** (`5.65s`); compileall passed; `pip check` reported no broken requirements. Local Uvicorn smoke-tested all 17 OpenAPI business paths: the 15 data/system paths available on the current ETM snapshot returned 200 and the GTFS-dependent map and journey search returned 503 as designed. This smoke test checked status and basic serialization, not every possible query combination.

The suite verifies algorithms and API contracts, but not real bus occupancy. There are no authorized Delhi GTFS files in the workspace, so schedule behavior has synthetic-feed integration coverage only. ETM destination labels and trip identity have not been validated; predictive occupancy accuracy cannot be calculated. Any test fixture values must remain isolated from `datasets/` and `outputs/`.

The trip-grouping stress script constructs known synthetic truth and a missing-vehicle share close to measured ETM missingness. Pairwise metrics demonstrate how grouping thresholds trade false merges for false splits; they are not Delhi inference accuracy. Reproduce with `python -m scripts.trip_reconstruction_stress_experiment`.

## Release checks

- Ensure all tests pass and inspect failures rather than suppressing them.
- Run the ETM pipeline against a private copy of the supplied source; reconcile input/retained/excluded counts and source SHA-256.
- If an authorized GTFS feed is supplied, inspect report issues and verify calendar boundaries and service dates before enabling journey search.
- Smoke-test `/health`, `/ready`, OpenAPI and every documented API against the processed database.
- Confirm errors for missing GTFS are explicit and no crowd-unavailable value defaults to zero.
- Record Docker build/runtime as unverified until Docker is available and run on the intended deployment platform.
