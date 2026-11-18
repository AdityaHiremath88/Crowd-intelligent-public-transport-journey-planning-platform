# Ticket records, demand summaries, and crowd estimates

## Current ETM data

The local source file is the October 2026 Delhi ETM export. It contains 2,559,899 records over October 1–31, 2026. The input fields are retained in DuckDB in `etm_records`; derived stop summaries are stored in `stop_demand`.

`passenger_count` is summed separately from `COUNT(*)`. The first is the passenger volume represented by ticket rows; the second is the transaction-row count. `start_stop_name` is treated as a source label only. Its physical meaning and its match to a GTFS stop have not yet been independently validated.

The observed `created_at` values carry a +05:30 offset and span the full month. This pipeline uses that field as **transaction time**, not boarding time. Demand summaries are grouped by transaction date, hour, weekday, route and ticket start-stop label. They describe recorded ticket activity; they do not estimate the number of people waiting at a stop.

The descriptive within-month checks show 97,630 recorded passengers per weekday on average (22 observed weekdays) and 67,305 per weekend day (9 observed weekend days). The highest transaction hour is 09:00–09:59 with 351,443 ticket rows. Mean daily recorded passenger volume is about 30,275 in the 06:00–09:59 window and 25,203 in the 16:00–19:59 window. These comparisons use transaction timestamps and are not boardings-by-hour or occupancy validation. The first and last weekly buckets are partial weeks.

The literal text `NULL` occurs in `vehicle_number`. Derived records normalize this marker to SQL NULL; the source rows remain preserved in `etm_source` during processing. 1,242,167 of 2,559,899 records have no usable vehicle number. Exact duplicate rows are investigated without deleting anything; this file has zero exact duplicate rows under equality across all nine source columns.

## Why onboard crowd predictions are unavailable

The export has route and vehicle labels, but no reliable individual trip ID or verified boarding timestamp. A vehicle may make multiple trips, and this export does not tell us which trip a ticket belongs to. Ticket destinations are not confirmed alighting events, and ticket data does not represent passengers who were not issued a captured ticket. Therefore the current system does not reconstruct segment occupancy or assign the four crowd categories.

Those estimates require a validated GTFS feed, stop/route matching, defensible trip inference, and an explicit confidence/coverage policy. Even then, reconstructed ticketed load would be a proxy, not ground-truth occupancy. Capacity-based labels additionally require verified vehicle capacity. No seats, percentages, live crowd levels, or Delhi journey predictions are fabricated.

## Confidence and validation

At present, stop demand responses carry `descriptive_observation`, which means an aggregate of observed ticket rows and is not a predictive confidence score. A future load estimate must report observation coverage, matching quality, trip inference quality, temporal data age and consistency across comparable service days. Raw ticket count alone is insufficient.

The official Delhi OTD documentation says static stop times are rough estimates based on assumed constant speed. Scheduled journey results must surface that limitation and must not be described as live ETAs.

