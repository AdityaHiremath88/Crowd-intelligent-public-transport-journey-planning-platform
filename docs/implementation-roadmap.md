# Backend implementation roadmap

This roadmap is based on `backend-audit.md`. Sequence is evidence-driven; an unavailable upstream feed does not block backend improvements that can be verified independently.

## Completed in this engineering phase

- Audited backend source, data layers, DuckDB tables, routes, schemas, scripts, tests and docs.
- Recorded repository/data risks and decisions.
- Verified official Delhi OTD publication, GTFS timetable warning, static-data freshness shown by the portal, and static-data access conditions.
- Documented the gap between historical transaction demand and physical passenger load.
- Corrected journey-ranking initial-wait accounting and added source/run metadata, historical aggregates, API capabilities, and supporting documentation.

## Implementation sequence

1. **ETM reproducibility (implemented):** source SHA-256, size, pipeline/schema version, append-only run row, transactional table rebuild, explicit retained/excluded counts, no implicit deduplication.
2. **ETM descriptive analysis (implemented):** daily/hourly coverage, ticket type and AC flag, weekday/weekend day-level bootstrap intervals and sample sizes with semantic caveats.
3. **GTFS quality (implemented; no real feed loaded):** structural/cross-file validation and service-window metadata; fail closed for schedule-critical and unsupported frequency/transfer feeds.
4. **Routing (implemented with limits):** bounded timetable search up to three transfers, service exceptions, overnight times, initial waits and ranking. Operational feasibility cannot be assessed without a real feed.
5. **API contract (implemented):** versioned endpoint schemas, capabilities, dataset provenance, methodology, explicit errors and OpenAPI-backed examples.
6. **Benchmarks (implemented):** local actual-database warm-cache direct-handler measurements and measured corridor aggregation optimization.
7. **Validation (in progress):** expanded synthetic edge fixtures and actual ETM reprocessing are complete; final HTTP smoke and full suite are being rerun.
8. **Delivery (in progress):** source catalog, technical docs, environment/container guidance, limitations and frontend integration contract are being synchronized.

## Data-dependent work that remains conditional

- Load actual GTFS only after an authorized archive is supplied; verify publisher metadata, terms, feed dates, schedule quality and source hash first.
- Review stop and route match candidates with human/operator context before publishing crosswalks.
- Attempt trip reconstruction only after receiving either a validated trip/waybill identifier or synchronized AVL/GPS/schedule and boarding-event evidence.
- Estimate segment passenger flow only after boarding/alighting events can be mapped to trip stop sequence. Validate against APC/manual counts before calling it occupancy.
- Calibrate crowd bands and confidence on independent service days and ground truth; otherwise return unavailable.

## Acceptance gates

- ETM pipeline is repeatable, source-hashed, transactional and reports retained/excluded totals.
- GTFS importer validates schedule criticality and makes invalid feeds unavailable; optional files are audited even when not required.
- Journey options are feasible against service calendar and stop sequence, and ranking includes initial wait without implying crowd optimization.
- HTTP contracts are listed in OpenAPI and docs; no API serves stale/synthetic real-world claims.
- Benchmark measurements are reproducible and no performance improvement is claimed without measured evidence.
- Test suite passes; frontend integration contract describes absent data plainly.


