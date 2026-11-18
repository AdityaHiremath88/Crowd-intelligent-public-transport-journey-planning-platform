# Bus-trip reconstruction research

## Problem and candidate methods

The target is a particular run of a bus vehicle through an ordered stop sequence, not a route label or an hour bucket. A passenger record would need an identifiable vehicle and a trustworthy timestamp/place event that can be aligned to a GTFS trip or AVL trajectory. Relevant methods in the literature join automatic fare collection (AFC/ETM) with automatic vehicle location (AVL), correct clock offsets, map-match to stops/route direction, then assign records to candidate trips probabilistically. Delhi bus-demand research using DIMTS ticketing records demonstrates demand analysis at line/route level; it does not turn every ETM transaction into a known individual trip. A 2025 Indian ETM harmonization study highlights cross-system variation in trip/route/time/stop fields.

Research references:

- Suman & Bolia, Delhi demand case study summarized in [Public Transport Operations After Lockdown](https://pmc.ncbi.nlm.nih.gov/articles/PMC7290149/).
- Fedujwar et al., [ETM data standardization across Indian urban transit](https://faculty.iitr.ac.in/~amitfce/pdfs/FedujwarEtc2025ETMStruCTRG.pdf).
- [AFC destination estimation with data fusion](https://onlinelibrary.wiley.com/doi/10.1155/2020/8305475) uses multiple evidence sources; that evidence is unavailable here.
- [GTFS Schedule Reference](https://gtfs.org/documentation/schedule/reference/) defines scheduled trips/calendars; [GTFS-RT Reference](https://gtfs.org/documentation/realtime/reference/) defines vehicle and trip update entities.

## Methods considered

| Method | Required evidence | Main failure mode | Decision for current data |
|---|---|---|---|
| Vehicle + route + short time window | Stable vehicle ID and boarding time | Same vehicle does multiple runs; time can be ticket issuance lag; direction/route label may change | Rejected as an individual-trip identifier. Useful only as a descriptive diagnostic. |
| Route/direction + scheduled departure proximity | Reviewed ETM-to-GTFS route/direction, validated stop and event timestamp | Schedule is approximate, transaction timestamp may lag, missing dwell/traffic, multiple trips near | Not implemented for crowd assignment; could produce candidate trips with probabilities after calibrating against run labels. |
| Vehicle trajectory map-matched to GTFS shape/stop sequence | Timestamped GPS/AVL, vehicle identity, trip/route/direction, spatial reference | GPS gaps, route deviations, shared corridors, clock drift | Not possible; no authorized AVL/GPS data supplied. |
| Supervised/probabilistic entity resolution | Ground-truth ticket-to-trip assignments or strong labels, features and calibration set | Label leakage, temporal drift, uncalibrated probability, missing-not-at-random vehicles | No model trained; no labels available. |
| Time-window clustering on ticket records | verified boarding timestamps, stop/route event patterns, independent run validation | Clusters do not equal trips; creates false certainty | Rejected for production. |

## Current implementation and output

`app/data_pipeline/trip_inference.py` accepts a source trip ID only as `identified_unvalidated`; it refuses to mint a trip ID from vehicle + route + transaction time. `scripts/assess_trip_inference.py` quantifies ambiguity in the actual export. The October dataset has no trip ID, transaction time is unverified boarding time, and vehicle number is null for 48.5% of rows. In the vehicle-day subset with a vehicle value, 147,824 of 181,620 vehicle-days have multiple route labels (2.577 average labels/vehicle-day). This is an ambiguity signal; legitimate service/direction assignment may explain some variation, so it is not a measured misassignment rate.

**Output for present ETM:** individual-trip inference is `unavailable`. It is not a prediction model and has no precision/recall metric because no labeled trips exist.

## Future probabilistic candidate design (not currently active)

If approved evidence arrives, candidate scoring could combine exact vehicle, route crosswalk/direction, observed event-to-schedule time residual, stop proximity, route shape distance, GTFS service-active status and trip continuity. For candidate trips `j`, a calibrated posterior would require:

`P(trip=j | ticket, AVL, schedule, matching evidence)`

Training/validation must split by calendar day and preferably hold out vehicles/routes; compare top-1 accuracy, top-k recall and calibration (Brier score/reliability plot). Unmatched/ambiguous records remain unassigned. Do not sum fractional posteriors as exact people unless the expected-load interpretation and uncertainty are explicitly carried forward.
