# Segment-level passenger-load methodology

## Quantities that must remain distinct

1. **Ticket transaction count:** number of exported ticket rows.
2. **Ticket passenger volume:** sum of `passenger_count`; business meaning requires the source dictionary.
3. **Boarding demand:** observed/estimated boardings at a stop and time. Current data can only provide a transaction-start-label proxy.
4. **Estimated ticketed passenger flow/load:** ticketed passenger journeys assigned to one trip and spans of its ordered stop segments.
5. **Physical onboard occupancy:** passengers physically aboard the vehicle, including passengers not captured in this export. It is not measured here.

## Mathematical foundation

For trip `t`, stop sequence positions `i`, boardings `B[t,i]` and alightings `A[t,i]`:

`L[t,i+1] = L[t,i] + B[t,i] - A[t,i]`

Given ticket journey `j` with validated board position `b_j`, proxy alight position `a_j`, and passenger volume `p_j`, direct segment load proxy is:

`L_hat[t,i] = sum_j p_j * 1[b_j <= i < a_j]`

For adjacent ordered GTFS sequence values, an interval contributes only if `board_sequence <= segment_from` and `alight_sequence >= segment_to`. This avoids counting a journey that alights before the complete segment. `app/crowd_model/load_estimator.py` implements this evidence-gated calculation over normalized journey inputs.

## Current evidence gate and output

The estimator requires an explicit `expected_trip_id`, unique increasing trip stops, positive passenger counts, valid increasing journey bounds present in that trip sequence, and no duplicated transaction IDs when IDs are supplied. It returns `ticketed_load_proxy`, not occupancy. Without a validated trip ID it returns unavailable. This pure function is not connected to the actual October ETM rows because no valid trip assignment or validated stop sequence is available.

## Assumptions and uncertainty

- Ticket `start_stop_name` is not independently confirmed as physical boarding.
- Ticket destination is only a proxy for alighting and may differ from actual passenger alighting.
- The ETM export may omit pass holders, uncaptured tickets or other rider classes.
- `passenger_count` semantics and transaction-to-boarding lag are unconfirmed.
- Independent buses may share route labels; route labels do not identify direction or trip.
- A bus may begin service with load already onboard; no origin-load evidence exists.
- APC/manual validation and vehicle capacity are absent.

The estimator currently sums only known ticketed journeys; it cannot correct coverage bias or estimate missing passengers. Unknown data must not be imputed as zero or a low crowd level.
