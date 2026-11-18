# Ground-truth data requirements

## Minimum for route-segment passenger flow

An authorized, privacy-reviewed observation feed needs one record per observed vehicle stop event, with stable keys and explicit semantics:

| Field | Requirement |
|---|---|
| `service_date`, `event_timestamp` | Local timezone/UTC offset and clock synchronization/error documented; event type timestamp must mean arrival/door count, not ticket transaction. |
| `vehicle_id` | Stable pseudonymous ID scoped to a retention period; map to actual vehicle configuration only in restricted storage. |
| `trip_id` / run or waybill ID | Stable operational run key, plus mapping to GTFS trip/service where it exists. Must distinguish repeated runs by one vehicle. |
| `route_id`, `direction_id`, `stop_id`, `stop_sequence` | Authoritative and versioned reference to the schedule/network; record match method and ambiguity. |
| `boardings`, `alightings` | Counts by stop event; document sensor/manual method, null/invalid flags, and whether mobility devices/crew are counted. |
| `onboard_load` or opening load | Needed if the observed trip begins with passengers already on board; otherwise load can be initialized from a verified terminal zero. |
| `source_quality` | Sensor health, completeness, duplicate status, correction provenance, device model/software and confidence/quality flags. |
| `capacity` | Vehicle-specific usable capacity and definition (seated/standing design or operational threshold), effective dates and configuration. Needed for occupancy ratios. |

Example proposed restricted stop-event table (schema only; values are placeholders, not Delhi observations):

```text
feed_version,service_date,trip_id,vehicle_key,route_id,direction_id,
stop_id,stop_sequence,event_time,boardings,alightings,onboard_load,
capacity,observation_method,quality_flag
<version>,<date>,<run>,<pseudonymous vehicle>,<route>,<direction>,
<stop>,<sequence>,<timestamp>,<integer>,<integer>,<integer>,<integer>,<APC|manual>,<flag>
```

## Minimum manual validation sample

Sample complete one-way trips and independently record boardings and alightings at each door/stop, vehicle/run identity, start/end load, count method and observation time. Stratify by operator, vehicle/APC model and configuration, route, direction, weekday/weekend, peak/off-peak and load range. Include high-load trips; document sample selection and rejected trips. Double-observer or video adjudication on a subset estimates manual-label error. The FTA's annual/triennial benchmarking manual is a useful reference, but its exact compliance sample rules apply to US NTD reporting and are not automatically Delhi requirements.

## Validation split and metrics

- Keep complete trips together; never split stop events from the same trip across train/test.
- Use chronological held-out service dates, plus held-out vehicles/routes where data volume allows.
- Report event-level boarding/alighting MAE and bias; accumulated-load MAE/RMSE and signed drift by stop index; maximum absolute load error; capacity-class confusion and calibration only after capacities/labels are validated.
- Report coverage, sensor failures, missing stops, match confidence and abstentions alongside accuracy.
- Use vehicle/day or trip block bootstrap intervals; ticket rows within one run are correlated.
- Pre-register thresholds and do not tune them on final test data.

## Privacy and governance

Prefer aggregated stop/trip counts over passenger-level trajectory records. Pseudonymize vehicle keys in analysis outputs; exclude passenger identity/payment identifiers entirely. Obtain written authorization, purpose/retention limits, security controls, legal basis and publication rights before acquisition. Public outputs should suppress small cells where re-identification is plausible. No such ground-truth data is currently present in CrowdWise.

## References

- [FTA NTD APC benchmarking reference](https://www.transit.dot.gov/sites/fta.dot.gov/files/2025-08/2025%20NTD%20Mthly-Wkly-Ref-Manual_20250828.pdf)
- [Caltrans APC data quality report](https://dot.ca.gov/-/media/dot-media/programs/research-innovation-system-information/documents/research-results/task3902-rrs-09-22-a11y.pdf)
- [Empirical bus APC validation study](https://opentransportationjournal.com/VOLUME/13/PAGE/250/?doi=10.1126%2Fsciadv.adg2248)
