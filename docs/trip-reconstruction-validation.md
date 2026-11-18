# Trip-reconstruction validation

## Current feasibility assessment

The reproducible diagnostic is `python -m scripts.assess_trip_inference`; current output is `outputs/trip_inference_assessment.json`.

| Evidence | Measured result | Validation consequence |
|---|---:|---|
| Source ETM rows | 2,559,899 | Single monthly extract. |
| Rows without usable vehicle label | 1,242,167 (48.5%) | Cannot use vehicle continuity for nearly half of records. |
| Vehicle-days with vehicle | 181,620 | Grouping unit is diagnostic only. |
| Vehicle-days with multiple route labels | 147,824 (81.4%) | Vehicle/day group is not a single route/trip. Direction/route ambiguity requires review. |
| Distinct route labels per vehicle-day | Mean 2.577 | Route/time grouping alone cannot isolate one run. |
| Adjacent vehicle/route/day ticket gaps | p50 650 s; p90 12,214 s; p99 34,175 s; 177,262 gaps >1h | Events occur over repeated-day operating patterns; adjacency is not proof of same run. |
| Explicit trip ID | absent | No direct key for trip validation. |
| Verified boarding timestamp | absent | Schedule-time residual cannot be interpreted as departure lateness. |

## Why accuracy cannot be scored

No independent trip labels, waybill/run IDs, synchronized GPS trajectories, driver logs or verified boarding event times exist in the local export. A reconstruction cannot have defensible precision/recall, and transaction counts cannot substitute for labels. Current status is `unavailable`, not “low accuracy.”

The controlled test in [trip reconstruction feasibility](trip-reconstruction-feasibility.md) uses synthetic runs to show sensitivity of simple grouping keys. Its precision/recall values are test-construction diagnostics only and must not be quoted as model performance on Delhi data.

## Future validation protocol

1. Obtain operator-authorized records containing trip/waybill ID and timestamp semantics; document privacy and access terms.
2. Link each source event to an authoritative GTFS trip and stop using stable IDs and direction, retaining unmatched and ambiguous records.
3. Select a stratified validation sample across vehicles, routes, times, weekdays/weekends and missingness.
4. Have an independent operations reviewer verify the actual run/stop assignment; keep adjudication labels out of feature engineering.
5. Split train/calibration/test chronologically and by vehicle or route to test generalization, not random row leakage.
6. Report top-1 accuracy, top-k recall, abstention rate, calibration error, coverage, false-merge and false-split rates with confidence intervals by subgroup.
7. Apply an explicit abstention threshold. Poorly matched tickets stay unassigned and do not contribute to segment loads.

No future method should infer a trip by assuming all events in one route-hour belong to one bus.
