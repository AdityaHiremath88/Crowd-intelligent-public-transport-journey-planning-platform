# Backend query performance report

## Scope and environment

Repeated on 17 Nov 2026 against the local October ETM DuckDB (**182,726,656 bytes**; 2,559,899 rows), Python 3.12.16, DuckDB 2.0.0, Windows x64, Intel64 Family 6 Model 142, four logical CPUs. This corrects the stale 188,493,824-byte size in the previous report. ETM endpoint cases are local warm-cache direct synchronous handler calls, 21 repetitions; they exclude HTTP transport, JSON serialization, cold start, remote storage and concurrency. Times are milliseconds, median / empirical p95.

| Query | Output bound | Median | p95 |
|---|---:|---:|---:|
| Stop search | 100 | 39.758 | 54.333 |
| Stop demand page | 200 | 79.412 | 109.343 |
| Daily trends | 31 | 33.840 | 36.154 |
| Weekly trends | 5 | 34.673 | 35.886 |
| Peak hours | 24 | 36.180 | 41.087 |
| Corridor analytics | 20 | 60.332 | 66.182 |
| Route catalog | 50 | 64.159 | 66.812 |
| Route profile | 24 hourly + 7 weekday buckets | 78.805 | 83.506 |
| Service profile | 2 groups | 55.457 | 63.349 |
| Overview | 1 summary | 35.120 | 46.770 |

The previous paired corridor optimization experiment remains historical: 277.48 ms median for the prior aggregation versus 88.05 ms for the materialized path, a measured 68.3% reduction in that specific paired run. The current repeat measured 60.332 ms for the corridor handler; it is a separate workload/run and must not be used to recompute the paired reduction.

## Community, presence, real-time and forecast API workload

Five newer auxiliary handlers were measured over 21 repetitions against the local feature stores / real ETM database. Results are median / empirical p95 milliseconds. Community-store calls include local SQLite connection/session setup; they are not network measurements.

| Workload | Median | p95 |
|---|---:|---:|
| Community report list | 56.145 | 79.467 |
| Community crowd aggregate | 56.211 | 82.537 |
| Opt-in presence aggregate | 55.324 | 79.479 |
| Realtime feed-health status | 3.292 | 3.854 |
| Ticket-activity forecast freshness gate | 35.462 | 38.263 |

The local signal database contained no production crowd reports or presence signals during the final clean run. The endpoint smoke used one temporary report to verify creation/deduplication and deleted it immediately; these values are handler timings, not throughput guarantees.

## Routing and GTFS importer workload

No real Delhi GTFS was available. The benchmark therefore uses isolated synthetic data, never served as application results:

| Workload | Fixture | Result | Memory / caveat |
|---|---|---:|---|
| Warm indexed journey query | 16,833 synthetic trips / 403,992 stop events; bounded 1-transfer search; 5 repetitions | median 139.807 ms; p95 302.461 ms; 1 candidate journey | One-time index construction 1,283.188 ms; Python traced peak 40,136,136 bytes. Query traced peak 4,886,944 bytes. Does not include native DuckDB allocations/RSS. |
| GTFS import | Synthetic ZIP, 20,000 trips / 2,000 stops / 400,000 stop_times | 4,919.109 ms; ZIP 2,584,430 bytes; DuckDB 6,828,032 bytes; zero validator issues; marked schedule-usable | Synthetic throughput only. 400k stop_times approximates the scale of OTD's portal-reported 378,324, but does not represent the actual feed or file distributions. |

The synthetic journey workload has one designed feasible transfer path. It measures implementation cost, not route quality or Delhi performance. The search index is built once when schedule data is loaded and reused; a production feed still needs its own latency and memory benchmark. Current routing is bounded timetable label search, not full RAPTOR/CSA.

## Latest run details

The repeat was generated 18 Nov 2026 at 00:00 UTC using 21 repetitions for each handler and five journey searches. Machine: Windows x64, Intel64 Family 6 Model 142, four logical CPUs. Python allocation peaks for current ETM cases range from 981 to 82,034 bytes; realtime status 3,341 bytes; community/presence calls 2,674–3,056 bytes; forecast gate 3,655 bytes. Synthetic search index construction was 1,283.188 ms; its Python traced peak was 40,136,136 bytes. The temporary GTFS import completed in 4,919.109 ms.

## Method and limits

The benchmark sampled 21 elapsed-time observations per ETM query and five journey searches; p95 is an empirical percentile over small samples and is noisy. Python `tracemalloc` per-call peaks in the ETM workload ranged from 981 bytes (service profile) to 82,034 bytes (stop-demand page); it excludes DuckDB native allocations and OS page cache. RSS was not measured. There is no concurrent-client test or production hardware. These results are engineering diagnostics, not an SLA. Full JSON with min/max and allocation measurements is ignored local output `outputs/backend_benchmark.json` and can be regenerated.

## Optimization applied

ETM processing materializes `route_demand` and `route_stop_catalog`. Unfiltered corridor requests aggregate at route/day/hour granularity and join a small route-label summary rather than re-scan stop-demand rows for distinct stop IDs. Date-filtered requests retain the stop-level source so counts and filters remain exact. For routing, a sorted per-feed departure index reduces repeated trip scanning and is reused across requests; journey leg objects are materialized only when a label improves a stop's earliest-arrival frontier or reaches the requested destination.

## Reproduction

From project root, run `.venv\Scripts\python.exe -m scripts.benchmark_backend --repetitions 21 --report outputs/backend_benchmark.json`. The script calls current APIs against the processed real ETM and creates temporary, explicitly synthetic GTFS imports/search fixtures. Record OS, CPU, Python, DuckDB, database size, filters, cardinality and results. Do not run benchmark writes on the serving database. Add cold-cache, HTTP serialization, concurrency, RSS and realistic authorized-feed measurements before deployment capacity claims.


