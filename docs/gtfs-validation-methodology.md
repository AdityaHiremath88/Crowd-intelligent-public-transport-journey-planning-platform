# GTFS validation methodology

## Standard and implementation

The normative reference is the [GTFS Schedule Reference](https://gtfs.org/documentation/schedule/reference/). Delhi OTD publishes a core static feed structure and warns that static bus arrival/departure times are rough estimates using a constant-speed assumption ([OTD documentation](https://otd.delhi.gov.in/documentation/)). The project-specific audit lives in `app/data_pipeline/gtfs_loader.py`; DuckDB cross-table checks and table loading are in `scripts/process_gtfs.py`.

### Required for current scheduled routing

`agency.txt`, `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt` and at least one non-empty `calendar.txt`/`calendar_dates.txt`. The loader checks required columns, data rows, route name availability, duplicate archive basenames and parseable arrival/departure GTFS times including hours >=24.

The importer checks stop-time-to-trip and stop-time-to-stop references, trip-to-route and trip-to-service-calendar references, unique trip/stop sequence, positive integer stop sequence, time syntax, calendar date/weekday flags, trip stop-time presence and monotonic times. Invalid feed quality blocks schedule routing.

### Optional files

- `shapes.txt`: schema, coordinate ranges, positive point sequence and trip shape references are audited. The local schedule search does not currently construct a route geometry response.
- `transfers.txt`: stop references and nonnegative integer `min_transfer_time` are audited. The journey engine does not yet apply row-specific transfer rules; it uses a conservative fixed 300-second minimum between vehicle legs.
- `frequencies.txt`: syntax/headway is audited. Non-empty frequency service is marked unsupported and blocks the feed from scheduled routing; it is not silently treated as a static exact departure.
- `feed_info.txt`: schema is audited if present. Source/freshness fields should be retained in the validation report; a feed service window, not archive modification date alone, determines the query-date coverage.

## Validity versus usability

A ZIP may be structurally parseable but not suitable for a particular function. Missing/invalid stop coordinates affect map capability; malformed references/times/calendars affect routing. Current importer uses a conservative boolean usability gate. It does not certify the agency's schedule as operationally accurate. Run [MobilityData's GTFS Validator](https://github.com/MobilityData/gtfs-validator) as an independent report where practical; retain notices and version. It cannot establish data provenance rights or real-world timetable truth.

## Feed freshness

Record source URL, publisher, retrieval timestamp, SHA-256, `feed_info` metadata, calendar service window and last updated evidence. Reject a query date outside active service. Do not extend a feed's expiration date or treat an archive-fetch date as a service date. OTD's visible static portal dates are currently June 20, 2024; no current archive is present in this workspace.

## Current validation result

No actual Delhi ZIP was available to inspect. Only small clearly synthetic tests exercise the current importer/routing path. No statement about the actual current Delhi feed's presence of `stop_times.txt`, file counts, integrity or freshness is made.
