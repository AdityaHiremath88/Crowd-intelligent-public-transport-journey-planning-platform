# Technical decisions

## TD-001: Keep a modular monolith and DuckDB for this stage

**Decision:** Continue with FastAPI + DuckDB in one deployable backend.  
**Reason:** The available ETM export is an analytical file workload, and current query volumes do not demonstrate a concurrent-write or multi-user transactional requirement that warrants PostgreSQL or a queue. DuckDB can scan, aggregate and persist local analytical data with little operational overhead.  
**Consequences:** Each request uses a short-lived read-only connection. ETL owns writes. Do not run concurrent ETL and API writes against one file. Reassess PostgreSQL only if concurrent application writes, multi-instance serving, row-level transactional workloads or operational uptime needs are demonstrated.

## TD-002: Use transaction time only as transaction time

**Decision:** `created_at` powers ticket-transaction-time analytics, not boarding-time predictions.  
**Reason:** The supplied data dictionary does not establish a boarding event timestamp.  
**Consequences:** Hourly profiles are labelled transaction-hour. Trip reconstruction and crowd-by-time remain unavailable absent validated event semantics or synchronization evidence.

## TD-003: Do not infer trip IDs from vehicle + route + time buckets

**Decision:** A source trip key or equivalent operator evidence is required for an individual-trip load.  
**Reason:** Vehicles repeat runs, vehicle identifiers are missing in almost half the rows, transaction event time is not verified boarding time, and route labels may conflate directions/variants. Fixed time buckets can merge trips or split one run.  
**Consequences:** Trip inference returns unavailable for this feed; do not manufacture occupancy. Future probabilistic trip matching must preserve candidate probabilities and be validated against known trip assignments.

## TD-004: Keep ticketed passenger flow distinct from measured occupancy

**Decision:** Segment sums are named ticketed-load proxies and only calculated when ticket journey bounds refer to one validated trip.  
**Reason:** A ticket destination is not guaranteed actual alighting, ticket capture may be incomplete, and vehicle capacity is not supplied.  
**Consequences:** No exact occupied seats or percentages. Crowd categories require calibration and explicit coverage/confidence evidence; physical occupancy requires APC/manual ground truth.

## TD-005: Require usable GTFS quality metadata before routing

**Decision:** Schedule search requires a processed validation row and schedule-critical checks passed.  
**Reason:** Presence of four tables alone is not evidence of calendar validity, relational integrity, or valid times.  
**Consequences:** Missing/invalid feed and query dates outside its calendar window produce unavailable/503. Stop and route mapping remains manual-review gated.

## TD-006: Scheduled time is not live ETA

**Decision:** Journey response identifies GTFS static schedule as source and describes times as approximate.  
**Reason:** Delhi OTD explicitly says its static stop times are rough estimates under a constant-speed assumption.  
**Consequences:** Do not show real-time semantics or infer traffic-aware arrival predictions without authorized GTFS-RT/AVL.

## TD-007: Find feasible journeys before preference ranking

**Decision:** Filter journey feasibility using service dates, sequence, departure time and transfer buffer first; then score feasible candidates.  
**Reason:** Ranking cannot rescue an impossible connection. The current bounded implementation allows up to three transfers and uses one earliest-arrival label per stop per boarding round.  
**Consequences:** Initial weights are transparent, configurable assumptions. With crowd unavailable, crowd weight is omitted and remaining weights are renormalized and disclosed. The current bounded timetable implementation supports at most three transfers; fixed transfer buffer is 300 seconds.

## TD-008: Validate GTFS locally and optionally with the canonical community validator

**Decision:** Keep project-specific importer checks in Python/DuckDB and document MobilityData GTFS Validator as a second independent feed-quality check.  
**Reason:** The open-source validator checks specification notices, while CrowdWise additionally needs its own schedule database invariants.  
**Consequences:** External validator use is optional until a real feed exists; its Apache-2.0 software license does not grant rights to redistribute a third-party feed.

## TD-009: Preserve input data and never silently deduplicate

**Decision:** Source file remains immutable; cleaned/derived values are separate; no automatic row deduplication without a defensible key.  
**Reason:** Identical rows can be legitimate repeated tickets and no transaction ID exists.  
**Consequences:** Every run records source digest, row counts and transformation version; anomalies are flagged, not erased.
