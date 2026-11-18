# Trip reconstruction feasibility

## Question and current answer

Can each October ETM ticket transaction be assigned to one particular bus run and a route direction/stop sequence? **Not from the delivered fields with defensible validity.** The extract has no trip/run identifier, no verified boarding timestamp and a vehicle label missing on 1,242,167 of 2,559,899 rows (48.524%). A vehicle-day contains multiple route labels on 147,824 of 181,620 vehicle-days with a known vehicle (81.4%). A vehicle plus route plus date is therefore not a trip key.

`created_at` is a transaction timestamp. A transaction may be issued before, during or after boarding; the delay distribution is not measured. Ticket start/end strings are not reviewed GTFS stop IDs, and a destination is not verified alighting. Route strings contain directional-looking suffixes but their semantics are not validated. These facts jointly prevent reliable run boundaries and route-direction inference.

## Candidate method comparison

| Candidate | Required evidence | Could be tried with current file? | Main failure modes / decision |
|---|---|---|---|
| Source trip/run ID join | Stable ETM trip/waybill/run key plus authoritative run table | No, key absent | Best starting point if operator supplies it. Validate key uniqueness and run calendar before use. |
| Vehicle + route + service date | Complete vehicle ID, direction, true event time, run schedule | Diagnostic grouping only | Same vehicle runs multiple trips; 81.4% vehicle-days span multiple route labels. Never assign one vehicle-day to one bus trip. |
| Vehicle + route + fixed time window clustering | Stable vehicle, timestamp tied to boarding, route/direction, calibrated window | Only a synthetic sensitivity test | Arbitrary window causes false merges/splits; missing vehicles cause collisions or abstentions; unknown transaction delay destroys a time threshold's interpretation. |
| Route + time clustering | Stable route/direction and true boarding event | Synthetic comparison only | Confounds multiple buses/trips in same hour; empirically cannot score without labels. |
| GTFS schedule residual matching | Current complete GTFS, verified stop/time and vehicle or trip mapping | No | OTD warns published stop times are rough constant-speed estimates. With transaction time instead of boarding time the residual is not lateness or trip evidence. |
| AVL/GPS trajectory map matching | Timestamped positions, vehicle/trip identity, route geometry/stops, clock synchronization | No authorized positions obtained | Would support run continuity and direction; still requires map-match quality checks and stale-feed handling. |
| Probabilistic entity resolution | Candidate IDs, labeled match/nonmatch sample, calibrated priors and explicit abstention | No | A score without reference labels is not confidence; don't auto-assign tickets. |

## Controlled synthetic stress test

`python -m scripts.trip_reconstruction_stress_experiment` creates 18 synthetic events from three known synthetic runs, hides 50% of vehicle IDs (near the actual ETM missingness fraction), and samples artificial transaction delays. It compares route/hour, vehicle/route/hour and vehicle/route/15-minute keys by pairwise precision/recall. The fixed run is saved to `outputs/trip_reconstruction_stress_experiment.json`.

| Synthetic grouping rule | Pairwise precision | Pairwise recall | False merge pairs | False split pairs |
|---|---:|---:|---:|---:|
| Route + transaction-hour | 0.294 | 1.000 | 108 | 0 |
| Vehicle + route + transaction-hour | 0.462 | 0.533 | 28 | 21 |
| Vehicle + route + 15-minute bucket | 0.800 | 0.356 | 4 | 29 |

This is a counterexample/sensitivity demonstration, **not a Delhi prediction**. The 18 events and truth labels were created by the test; the delay distribution is illustrative and not estimated from the ETM. A short window reduces merging in this construction while splitting real synthetic runs. It shows why choosing a plausible threshold cannot establish accuracy.

## Validation gate

Current production inference function, `app/data_pipeline/trip_inference.py`, accepts a source trip key only as `identified_unvalidated`; without that key it returns `unavailable`. The key still needs authoritative validation before load estimation. This conservative behavior is appropriate.

Before enabling trip inference, require: (1) an authorized source key/run mapping; (2) timestamp semantics and clock timezone; (3) independent labeled runs spanning vehicles, routes and periods; (4) stop/direction candidates with reviewed identity; (5) chronological and vehicle-held-out evaluation; (6) pairwise false merge/split, top-k match, coverage and abstention metrics with grouped uncertainty; (7) acceptance criteria set before evaluation. Retain unmatched tickets.

## References

- [OTD GTFS documentation and static-time caveat](https://otd.delhi.gov.in/documentation/)
- [GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/)
- [Transit OD estimation with AVL/APC research](https://arxiv.org/abs/1911.05777) (requires AVL/APC-type observations; not applicable as a direct recipe for this ticket file)


