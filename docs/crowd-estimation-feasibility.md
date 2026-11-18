# Crowd estimation feasibility and evidence gates

## Distinct quantities

| Quantity | Definition | Supported now? | Product wording |
|---|---|---:|---|
| Ticket transaction volume | `COUNT(*)` records in a filtered source group | Yes | Transactions / ticket records. |
| Passenger ticket volume | `SUM(passenger_count)` represented by those rows | Yes, subject to field semantics | Recorded passenger volume represented by tickets. |
| Historical boarding-demand proxy | Ticket start-label volume grouped by transaction date/hour | Descriptive proxy only | Historical ticket-start activity; timestamp is not confirmed boarding time. |
| Estimated passenger flow | Alighting and boarding flow assigned to known route stops/trips | No | Unavailable until stop, event and trip linkage are validated. |
| Estimated onboard load | Passenger flow accumulated along one vehicle trip | No for present extract | Unavailable. |
| Measured occupancy | Sensor/manual count of physical riders at time/segment | No | Unavailable. |

## Flow equation and assumptions

For a validated trip with stop-ordered boardings `B_i` and alightings `A_i`, the load after stop `i` is:

```text
L_(i+1) = L_i + B_i - A_i
```

Equivalent ticket OD form for segment `s`: `L_s = sum(passenger_count_j * I(j's validated boarding-to-alighting path covers s))`. This only works if the passenger journey has the right trip, ordered boarding/alighting stops, and the records represent the population being counted. For ETM tickets, destination is a possible alighting proxy, not confirmed alighting; transaction start is not verified boarding time; the source has no trip ID and nearly half the vehicle labels are missing. Therefore this computation is **not run against the real October file**.

Useful invariants once validated counts exist: load cannot be negative; load after the final stop returns to zero for a closed trip; total boardings and alightings reconcile subject to onboard passengers crossing the observation boundary; passenger counts are nonnegative; stop sequence strictly increases; load never exceeds a validated usable capacity without a flagged anomaly. Do not silently clip negative or over-capacity values—flag and investigate.

## Present evidence readiness

| Evidence dimension | Current evidence | Gate result |
|---|---|---|
| Ticket row coverage | 2,559,899 rows across 31 dates; source transaction times span observed October | Descriptive aggregates only. |
| Stop identity | ETM strings, 7,148 starts and 6,941 destinations; unresolved spelling variants; no reviewed GTFS mapping | Stop-specific GTFS flow blocked. |
| Route/direction identity | 2,259 source route strings; directional suffixes are unverified | Directional load blocked. |
| Run identity | No trip ID; 48.524% vehicle labels missing; repeated routes per vehicle-day | Individual-trip load blocked. |
| Boarding timestamp | `created_at` is transaction time; delay unmeasured | Time-specific occupancy blocked. |
| Alighting observation | Ticket destination only | Actual alighting/load blocked. |
| Ticketing coverage | Passengers/transactions outside these records unknown; ticket type semantics unverified and only ID 1 occurs | Population coverage unknown. |
| Capacity | No vehicle capacity linked to vehicle ID/configuration | Occupancy percentage and capacity bands blocked. |
| Physical ground truth | No APC or manual onboard count export | Measured occupancy and calibrated prediction blocked. |

## What can be served now

Current stop/route/hour/date APIs may describe ticket volume and transaction count in the historical October extract. They must not return one of the four crowd labels. API capabilities explicitly mark trip-level load, crowd classification and live positions unavailable. The synthetic routing tests do not contain real-world crowd labels.

## Future implementation evidence gates

1. **Demand proxy:** the current minimum gate is a processed source, explicit measure and transaction-time caveat; already met.
2. **Ticketed segment-flow proxy:** reviewed ETM-to-GTFS stop mapping, validated route direction and ordered stop path, event-to-trip link, ticket semantics and documented coverage. Output must be named ticketed-flow proxy, with coverage and uncertainty; not physical occupancy.
3. **Estimated onboard load:** all above plus validated board/alight timing or a defensible estimation model and independent trip-level load labels. Include missing ticket coverage and uncertainty.
4. **Occupancy class/percentage:** load plus actual vehicle capacity for that specific vehicle/configuration and synchronized validation counts; calibration on held-out services and time periods. Never infer a percentage from route-relative rankings alone.
5. **Live crowd:** authorized, fresh AVL/APC (or equivalent occupancy feed), timestamp freshness policy, vehicle-trip matching and latency monitoring. Historical ETM must remain labeled historical.

## Research basis

The FTA [2025 NTD reference manual](https://www.transit.dot.gov/sites/fta.dot.gov/files/2025-08/2025%20NTD%20Mthly-Wkly-Ref-Manual_20250828.pdf) requires APC benchmarking against manual samples for its reporting context. California DOT's [APC data improvement report](https://dot.ca.gov/-/media/dot-media/programs/research-innovation-system-information/documents/research-results/task3902-rrs-09-22-a11y.pdf) discusses equipment/AVL integration, processing and periodic manual/video validation. The peer-reviewed [bus APC empirical study](https://opentransportationjournal.com/VOLUME/13/PAGE/250/?doi=10.1126%2Fsciadv.adg2248) compares stop boarding/alighting counts to manual observations and notes errors can propagate into accumulated loads. These sources support validation practice, not a claim about Delhi APC quality.
