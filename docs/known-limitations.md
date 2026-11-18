# Known limitations and blockers

## Data access and identity

- The actual ETM CSV is available locally (2,559,899 October 2026 rows); it contains transaction timestamps but no verified boarding timestamp or stable trip identifier.
- No authorized static Delhi GTFS ZIP is present. The DTC-linked Nov-2026 timetable PDF was obtained and hashed, but it is a human-readable document with no confirmed reuse licence; it has not been converted into or used as GTFS. Consequently no local GTFS stop IDs/trips/calendar are available to the API. Journey search and GTFS map stops correctly return unavailable.
- The Delhi OTD public download interface requests user/contact and purpose information; none was submitted. A previously known Transport Stack download endpoint returned 401. No access was bypassed.
- ETM start/end stop names have not been matched to GTFS. Fuzzy candidates require human review before any join.

## Crowd inference

- Demand aggregates are ticket-start record volume and transaction counts, not waiting passengers.
- `created_at` is not verified boarding time. Ticketed destination is not confirmed alighting.
- Vehicle identifiers are absent on 1,242,167 rows and one vehicle-day may span multiple route labels. Hourly grouping cannot recover bus trips. No individual trip or segment load is currently published.
- No vehicle-specific capacity or physical passenger count ground truth exists. Therefore occupancy percentages, empty seats, crowd categories and calibrated occupancy confidence are unavailable.
- Pass holders, unrecorded passengers, transaction failure, route/stop labeling and ETM fare semantics can bias recorded ticket totals.
- October is one month, insufficient for annual seasonality or long-term generalization. Ticket type values and `is_ac` business meanings are undocumented.

## Routing

- Router code is covered with synthetic feed fixtures only; there is no real Delhi feed to validate route feasibility or ETA quality.
- Schedule queries outside the loaded GTFS calendar start/end dates are rejected explicitly. A feed whose calendar extends into the future is not independently proven current; source freshness and publisher update metadata still require review.
- The timetable search is a bounded earliest-arrival boarding-round search supporting up to three transfers, not a production-optimized RAPTOR implementation. Transfers have a fixed 300-second buffer; GTFS transfer rules, walking paths, frequency-based trips and arrival-by search are not implemented.
- Import marks feeds with nonempty unsupported `transfers.txt` or `frequencies.txt` unusable for routing. Static scheduled times can be approximate and do not account for traffic or real-time updates.

## Operations and validation

- No real-world prediction accuracy can be claimed without independent later-period observations for demand or onboard counts for occupancy.
- Synthetic trip grouping metrics and synthetic timetable throughput are controlled software experiments only; they do not validate a Delhi feed or inferential accuracy.
- Benchmark figures are warm-cache, local, direct-handler measurements and exclude HTTP serialization/concurrency; native DuckDB memory was not measured.
- Docker is unavailable on the development host, so Docker build and runtime remain unverified.
- Database writes and pipeline runs should be serialized; DuckDB is not configured as a multi-process concurrent write service.


