# ETM quality assessment

**File inspected:** local October 2026 export, 2,559,899 rows.  
**Assessment limit:** field checks establish parse-level properties, not business semantics or operator coverage.

## Measured profile

| Check | Result | Interpretation |
|---|---:|---|
| Input/retained/excluded | 2,559,899 / 2,559,899 / 0 | No rows removed by current pipeline. |
| Timestamp coverage | 2026-10-01 00:00:01.796721 to 2026-10-31 23:58:22.450250, `+05:30` | Complete calendar-month span, but this alone does not prove all tickets/vehicles are included. |
| Timestamp parsing / distinct date and hour coverage | 31 dates, all 24 hours represented on each date | Sparse late-hour activity exists; complete clock coverage is not even sampling or complete service coverage. |
| Passenger count | min 1, max 6, mean 1.07567; median 1, p90 1, p99 3 | No values outside the observed 1–6 range; semantic validation still needed. |
| Passenger volume vs ticket rows | 2,753,606 vs 2,559,899 | Different measures; volume is the sum of the passenger_count field. |
| Vehicle number | 1,242,167 null-like rows (48.5%); 6,809 distinct remaining labels | Materially weak for vehicle continuity; route/hour grouping cannot substitute for a trip key. |
| Routes / start labels / end labels | 2,259 / 7,148 / 6,941 distinct normalized strings | String diversity suggests mapping burden; does not quantify incorrect matches. |
| Exact duplicates | 0 under all-nine-source-field equality | Does not rule out duplicate events when there is no transaction ID; no deduplication was applied. |
| Amount | 0 null/negative; min 0, max 133.5, p50 13.5, p90 22.5, p99 40.5 | Anomaly profile only. Currency and refund/concession semantics are not confirmed. |
| Ticket type | one distinct ID, `1` | No category comparison possible in this file; meaning unknown. |
| AC flag | true 2,059,092 rows (80.4%); false 500,807 | Records are skewed across the flag. Not a fleet/service share absent business semantics and coverage design. |
| Source nulls | no null start/end/route; vehicle null-like as above | Zero nulls in those fields does not imply labels are accurate or complete. |

## Within-month observed demand comparison

Daily aggregates show 22 weekdays and 9 weekend days. Mean `passenger_count` sum was 97,630/day on weekdays and 67,305/day on weekends. A day-resampling percentile bootstrap (20,000 resamples; fixed seeds `20261117` and `20261118` for passenger/transaction volume) gives descriptive 95% intervals for passenger volume of 90,101–103,571 on weekdays and 56,363–78,230 on weekends. Day-level transaction-count intervals are 83,801–97,013 and 50,420–72,310. These are intervals over observed calendar dates; weekdays/weekends have different sample sizes and day-level observations may be serially correlated. They are not forecasts or seasonal estimates.

The largest recorded transaction hour in the current report is 09:00–09:59 (351,443 ticket rows; 374,218 represented passengers). By source transaction hour, volume is also elevated at 18:00–19:59 (494,030 passenger volume across those two hours). Hourly differences are transaction-time profiles, not boarding-time peaks. Evening and morning comparisons are likewise descriptive.

## Ticket OD-label activity and segment feasibility

A DuckDB feasibility query (`scripts/analyze_etm_feasibility.py`) found 257,483 distinct exact source start/end label pairs, 7,148 start labels, 6,941 destination labels and 6,537 exact label strings present in both sets. The largest exact label pair was “West Patel Nagar” → “Karol Bagh Metro Station” (5,017 represented passenger volume; 4,479 transaction rows). This is a ticket origin/destination-label distribution only; it does not prove a physical stop match, individual trip, boarding time, actual alighting, or segment flow. Different spellings remain separate until reviewed. The full local query output is `outputs/etm_feasibility.json` (ignored local artifact).

There is only one observed `ticket_type_id` (`1`), so ticket-type comparisons are not identifiable from this month. The `is_ac` flag splits 2,059,092 records marked true and 500,807 false, but source business meaning and feed coverage are undocumented; these are not a fleet share, market share or AC crowd comparison. Route labels number 2,259 and should be analyzed as source labels, not canonical directions. Missing vehicle label count is 1,242,167/2,559,899 (48.524%).

Consequently useful current analyses include transaction-time label-pair rankings, historical route/start-label profiles, weekday/hour summaries and passenger-volume versus transaction-row comparisons. The dataset cannot identify onboard segment loads; see [crowd estimation feasibility](crowd-estimation-feasibility.md) and [trip reconstruction feasibility](trip-reconstruction-feasibility.md).

## Operational risks and disposition

1. **Schema inference:** `read_csv_auto` infers SQL types. Fail if unexpected types or parsing change materially; record the schema and compare it to expected types in processing.
2. **Semantics absent:** validate ticket count, amount, AC, route and stop definitions with the data publisher before attaching business meaning.
3. **Timestamp uncertainty:** need source event documentation and ideally validation against bus logs/AVL before aligning tickets to trips.
4. **Missing identifiers:** nearly half of rows have no vehicle number; remaining vehicle labels do not identify trips.
5. **Coverage bias:** ticketed transactions need not include all passengers or payment/pass channels. Do not infer systemwide riders from transaction totals without coverage evidence.
6. **Duplicate semantics:** zero exact duplicate rows do not validate event uniqueness.
7. **No independent ground truth:** no APC/manual counts are present; occupancy error metrics cannot be computed.

Current data is suitable for observed ticket-volume summaries with these caveats. It is unsuitable for measured queue, vehicle occupancy, legal capacity, spare seats or live crowd conclusions.


