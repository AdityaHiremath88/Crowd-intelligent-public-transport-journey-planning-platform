# Real-world validation plan

## Current state

The ETM pipeline and historical descriptive API can be validated for reproducible row accounting and aggregation on the supplied file. There is no current licensed GTFS feed, trip labels, APC count feed, capacity map or manual occupancy ground truth. Consequently, routing behavior is validated synthetically, while real-world trip reconstruction and occupancy predictive accuracy are **not measurable yet**.

## Stage gates

| Stage | Entry evidence | Evaluation | Release gate |
|---|---|---|---|
| 0. Reproducible ETM description | Source file/hash, schema, processing metadata | Re-run pipeline; row totals, exclusions, schema and aggregates match; inspect anomalies | All changed counts have a reason and source rows are retained/flagged. |
| 1. Stop/route reference | Authorized current dated GTFS + reviewed ETM label map | Referential integrity, exact/fuzzy review precision, unmatched and ambiguous rates by label/volume | No unreviewed fuzzy joins used in public flow analytics; feed dates cover requested dates. |
| 2. Trip assignment | Run IDs or AVL, timestamp meaning, adjudicated trip sample | Chronological and vehicle-held-out assignment; false merge/split, precision/recall, coverage, abstention, calibration | Thresholds fixed before evaluation; ambiguous events abstain; field coverage is reported. |
| 3. Passenger flow | Trip-matched stop board/alight counts and opening/closing loads | Stop-level reconciliation; negative loads; final-load drift; boarding/alighting and load error by subgroup | Errors and missingness meet operator-approved limits; no unexplained correction/clipping. |
| 4. Occupancy/crowd class | Stage 3 plus vehicle-specific capacity and independent simultaneous count | Load/occupancy error; class confusion, macro-F1, weighted error, calibration/reliability and subgroup metrics | Limits agreed with operator; adequate evidence for each class; out-of-domain abstention. |
| 5. Live service | Authorized fresh AVL/GTFS-RT/APC, identity join and latency monitoring | Feed freshness, trip match, position/map-match, end-to-end latency, stale/duplicate rates | Fail closed to unavailable when stale, unauthorized, unmapped or incomplete. |

## Statistical protocol

1. Freeze source bytes and provenance; version GTFS and ETM independently.
2. Define target, unit of analysis, observation window and semantics before examining test labels.
3. Use chronological holdout. Group all records from one vehicle/run/day together; where feasible report a second test on unseen vehicles/routes.
4. Compare with simple baselines (historical same route/time bucket for demand; persistence or observed previous stop for measured load if appropriate). Never claim a complex model wins without baseline comparisons.
5. Report point estimates and trip/day-clustered bootstrap intervals; include sample size, coverage and subgroup metrics.
6. Report abstention separately; a model can improve apparent precision by declining hard cases, so publish both accuracy and coverage.
7. Keep ticket volume evaluation separate from onboard load evaluation. Accurate ticket volume does not validate physical occupancy.
8. Revalidate after feed, vehicle, fare-system or sensor changes; monitor missingness and distribution shift.

## Demand analysis that is possible now

Use the current month for descriptive transaction-time/hour/day and stop/route-label patterns. Show passenger volume separately from row counts, use day-level variation rather than treating 2.56 million tickets as independent samples, and describe the October sample only. Do not make seasonal or causal claims from one month. If forecasting a later month, use rolling-origin chronological evaluation against weekday/time baselines and a future period not in model tuning.

## Pilot data collection

Run a limited authorized onboard count study on sampled complete trips, with a manual/video reference independent of APC; record stopwise boarding and alighting, observed load, vehicle configuration, scheduled and actual timestamps, GTFS/AVL identities, and sensor status. Stratify by route, direction, vehicle type, peak/off-peak and observed load. Reconcile count totals and clock alignment before modeling. Ensure consent/privacy, data minimization and deletion rules. The exact sample size should be based on desired error-bound precision and observed trip-level variance, not a generic ticket count.

## Stop/go review

Every deployment candidate needs a signed data-source/license review, data-quality report, chronological evaluation, explicit limitations, API abstention behavior and reproducible model/config hashes. Until stages 1–4 pass, the customer API must keep route search unavailable or clearly scheduled-only and crowd estimates unavailable; it must never emit invented Delhi predictions.
