# Crowd validation plan

## Ground truth needed

Minimum useful validation source is trip/time/segment-specific passenger counts from an authorized automatic passenger counter (APC), or structured manual counts by trained observers. Record vehicle, GTFS trip or independently matched run, stop sequence, count timestamp, load before/after stop, count method, uncertainty, and capacity source. Protect any sensitive identifiers and aggregate after linkage.

## Study design

- Stratify routes, directions, vehicle types, peak/off-peak, weekdays/weekends and service days.
- Sample multiple dates per stratum; define sample size from desired error interval and observed day/route variance.
- Synchronize observer/APC and ETM clocks, validate time zone and define whether counts occur at arrival, door close or departure.
- For each stop, independently record boarding/alighting and onboard count; reconcile `L_next=L_current+B-A` against direct sensor load.
- Retain route/trip/vehicle-matching failures as coverage outcomes rather than removing them silently.

## Metrics

- Continuous load: MAE, RMSE, signed bias, median absolute error and interval coverage by segment.
- Capacity class (only with verified capacity): macro-F1, per-class precision/recall, confusion matrix and calibration.
- Coverage: fraction of segments eligible, matched, and returning a non-abstained result.
- Confidence: calibration and coverage-risk curves; compare model confidence with actual residuals.
- Baselines: previous comparable service-day mean, route/time historical median, and no-estimate/abstain baseline.

Split chronologically, not randomly. Keep a final untouched test period and group correlated records by trip/day. Report confidence intervals via trip/day block resampling. No metric can be populated from the current ETM extract alone.
