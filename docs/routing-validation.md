# Routing validation

## Existing automated evidence

`tests/test_journey_search.py` and `tests/test_gtfs_end_to_end.py` use clearly synthetic trips/feed and cover:

- GTFS calendar weekdays and exception removals;
- after-midnight hours >=24 and conversion to local clock datetime;
- direct route feasibility;
- one- and two-transfer paths with minimum buffer;
- inactive service and insufficient transfer-time rejection;
- max-transfer input bound;
- ranking preferences with crowd unavailable and initial waiting-time contribution;
- import -> DuckDB -> schedule service -> journey API response with synthetic provenance.

## Validation properties

For every returned option, validate in tests that all legs follow ordered GTFS stops, the selected service is active for its service date, each transfer is at the shared stop, and next departure is at least the configured buffer after previous arrival. Duration is elapsed from first scheduled vehicle departure to final arrival, includes inter-leg layover, and excludes initial wait; `waiting_seconds` includes initial and inter-leg wait. Preference score uses elapsed time from requested departure including initial wait plus transfer count when crowd is absent.

## Limitations and next checks

- No actual Delhi GTFS feed exists locally. No live journey route/time has been validated.
- Row-specific `transfers.txt` rules and frequency-based trips are not supported; frequency feeds are blocked rather than silently approximated.
- Single earliest label per stop/round cannot preserve crowd-diverse alternatives once segment data arrives.
- Request arrival-time search, walking connections and multi-agency transfer rules are not provided. The bounded three-transfer path limit is not full Pareto RAPTOR and does not retain crowd-diverse alternatives.
- GTFS times may be rough approximations per OTD; calendar feasibility does not guarantee a bus actually operates as listed.

Next: add random tiny feed property tests, compare against a trusted small-feed reference router, validate every generated journey end-to-end, and performance test on an authorized full feed.


