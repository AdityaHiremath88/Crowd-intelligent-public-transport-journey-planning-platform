# October Delhi ETM data dictionary

## Provenance and scope

The local file is `datasets/etm/raw/October-Delhi.csv` (2,559,899 records; 290,014,457 bytes). Its archive and source URL are recorded in `docs/data-sources.md`. The exporter/publisher data dictionary and licence were not included, so definitions below distinguish observed storage from semantic interpretation. Values in this document are measured from the current local file, not generalized to all Delhi buses.

| Field | Observed data / processing | Safe interpretation | Open questions |
|---|---|---|---|
| `passenger_count` | Integer after DuckDB parsing; observed range 1–6; sum 2,753,606 | Passenger-volume value represented by transaction rows, as supplied by the field | Whether this is riders per ticket, ticket-party size or another ticket metric needs publisher confirmation. Do not call row count riders. |
| `amount` | Numeric; observed min 0, max 133.5, sum 34,176,078; 0 negative/null in current parsed export | Numeric transaction amount field | Currency, concession, refund, fare-stage and amount units are not documented; don't label as rupees/revenue without confirmation. |
| `vehicle_number` | Normalized uppercase/trimmed; blank, `NULL`, `NA`, `N/A` become SQL NULL. 1,242,167 rows null. 6,809 distinct non-null values. | Source vehicle label where populated | Registration identity correctness, reassignment and whether ID persists through a whole trip are unknown. It is not a trip ID. |
| `ticket_type_id` | Integer; current file contains one value, ID `1`, on all 2,559,899 rows | Source category identifier | Category meaning is undocumented. No semantic label assigned. |
| `start_stop_name` | Trimmed and internal whitespace collapsed; 7,148 distinct normalized labels; no nulls observed | Ticket `start` label used as a historical ticket-start grouping | Whether this is confirmed boarding stop is unknown; labels are not matched to GTFS IDs. |
| `end_stop_name` | Same conservative whitespace normalization; 6,941 distinct labels; no nulls observed | Ticket `end` label | Whether it is intended/actual alighting is unknown; do not treat as confirmed alighting event. |
| `route` | Trimmed, uppercase, all whitespace removed; 2,259 distinct labels; no nulls observed | Normalized source route string | May encode direction, variants, vehicle service or inconsistent operator labels. It is not a GTFS route_id. |
| `created_at` | Parsed as timezone-aware timestamp; observed offset +05:30 and dates Oct 1–31 | Ticket transaction timestamp for analytics | Boarding event timing and transaction-to-board latency are unverified. |
| `is_ac` | Boolean after parsing; `true`: 2,059,092 rows; `false`: 500,807 | Source AC flag category | Not linked to vehicle capacity/identity, and no AC-specific demand should be generalized without validating field semantics. |

## Derived tables

- `etm_records`: cleaned/normalized row-level values plus `transaction_local_time`, `transaction_date`, `transaction_hour`, and `transaction_weekday_sunday_zero`. It retains one row per source row; there is no automatic deduplication.
- `stop_catalog`: stable opaque `etm_<sha256-prefix>` ID and normalized start-stop label. ID is not a GTFS stop ID.
- `stop_demand`: group by opaque start label, route label, weekday (Sunday=0), transaction hour, transaction date. `passenger_volume` is `SUM(passenger_count)`, while `transaction_count` is `COUNT(*)`.
- `route_demand`: group by route label, date, transaction hour and weekday, retaining passenger volume and transaction count separately.
- `route_stop_catalog`: distinct route/start-label pairs used for route summaries; these labels are not verified physical stops.
- `daily_demand`: daily passenger volume and transaction count.
- `hourly_demand`: date/hour/weekday passenger volume and transaction count.
- `service_profile`: date/hour/source `is_ac`/`ticket_type_id` dimensions; source field semantics are unverified.
- `data_quality`: one current ETM aggregate-quality row.
- `pipeline_runs`: append-only run metadata for ETM and GTFS processing, including source hash, byte size, schema/pipeline version, row counts, outcome and runtime.

Raw CSV remains the immutable raw layer and must be retained separately. The ETL layer is a normalized analytical representation, not an exact raw replica: source strings are not all retained in `etm_records`; rebuild from the private immutable CSV if needed.
