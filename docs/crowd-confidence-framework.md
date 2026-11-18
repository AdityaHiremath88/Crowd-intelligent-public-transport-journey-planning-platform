# Crowd confidence framework

## Evidence components

`app/crowd_model/confidence.py` represents candidate evidence dimensions:

- independent comparable service days;
- coverage fraction over required route/stop/time observations;
- stop match quality;
- route/direction match quality;
- trip identity/inference quality;
- comparable-day consistency;
- data age/freshness.

The function deliberately does not use raw ticket transaction count as the confidence input. Current stored coefficients and low/medium/high boundaries are illustrative engineering choices only. The weighted output is a heuristic evidence index, **not a probability**, confidence interval, calibrated model confidence or promise of correctness.

## Production rule

The API currently publishes no onboard-load confidence value. Core stop, route, trip and independent validation evidence are missing, so `assess_confidence` correctly returns unavailable when these dimensions are absent. Do not treat the illustrative score's level label as a validated public prediction. The `/api/v1/system/capabilities` and `/api/v1/system/methodology` endpoints state this limitation.

The actual October export supports descriptive ticket-volume coverage (31 calendar dates and 24 observed transaction hours), but this does not compensate for missing trip identity, unverified event time, ticket-population coverage or absent physical load labels. See [crowd estimation feasibility](crowd-estimation-feasibility.md) for release gates.

## Future calibration

1. Define a target label (prefer measured onboard load or a documented capacity class) and measurement protocol.
2. Use separate calibration and test periods by service date, and hold out routes/vehicles for out-of-domain evaluation.
3. Calibrate probabilities with a method suitable for sample size; assess Brier score, log loss, reliability curves and subgroup coverage.
4. Estimate uncertainty intervals with day/vehicle-level resampling rather than treating correlated ticket rows as independent.
5. Define abstention criteria for low matching, low coverage, stale feeds and out-of-distribution cases.
6. Store calibration dataset hashes, model/version, target definition, date range, sample counts and evaluation metrics.

## Limitations

Missingness is not random: vehicles without identifiers or passenger groups not represented in tickets may systematically differ. No mathematical weighting can recover unobserved riders without external coverage data. A high ticket count alone cannot compensate for missing trip identity or poor stop matching.
