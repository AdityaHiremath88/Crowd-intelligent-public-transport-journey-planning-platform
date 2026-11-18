# Static GTFS journey planning integration

## What is connected

This section records a prior local GTFS validation. The raw ZIP and processed database are excluded from Git and are not present in the current checkout, so the earlier load cannot be reproduced here until an authorized archive is supplied again. CrowdWise does not treat this historical report as evidence that schedules are currently available.

The loaded archive has SHA-256 `8eb05d9c21e7a6b42d7b49de45cb095b70ddee5b8f7716859330c9784c322f05`. It contains two agencies, 6,862 stops, 2,574 routes, 80,357 trips, 2,737,136 stop-time rows and 965,607 shape points. The feed's `feed_info.txt` reports version `v32` and a service window of 2025-01-01 through 2040-01-01. The import passed the application's routing quality gate with zero detected issues after the importer was corrected to accept GTFS stop sequence zero and ignore macOS `._` archive metadata.

## API behavior

- `GET /api/v1/system/capabilities` reports `scheduled_journey_search: true` when the imported feed passes validation.
- `GET /api/v1/stops?q=...` searches the GTFS stop catalog and returns stop IDs and listed coordinates when a validated archive is loaded.
- `POST /api/v1/stops/nearby` finds a nearest listed stop after an explicit browser-location request; query coordinates are not retained.
- `POST /api/v1/journeys/search` returns schedule-based journey options, route labels, stop names, and scheduled times.
- A GTFS stop does not automatically receive historical ETM ticket activity. Until a stop crosswalk is reviewed, that demand lookup returns HTTP 409; the frontend explains the missing match.

The live backend was checked after installation. Searching stop IDs `1` to `2` for 2026-11-18 returned scheduled options. The first was route `102ADOWN`, departing 06:05 local time, with `eta_source` set to `GTFS scheduled times (approximate)`.

## Accuracy and source limits

The [GTFS Schedule Reference](https://gtfs.org/documentation/schedule/reference/) defines the feed format; it does not host or certify Delhi's dataset. This feed was already present in the user's local downloads. Its permission/provenance and freshness have not been independently confirmed. Delhi OTD describes its published bus stop times as rough estimates generated with constant-speed assumptions in its [documentation](https://otd.delhi.gov.in/documentation/). Its [static feed page](https://otd.delhi.gov.in/data/static/) has listed an older update date, so the feed's future calendar range must not be read as proof that routes/times are current.

Stop coordinates are GTFS publisher-provided values. Structural checks confirm they parse and fall within valid latitude/longitude ranges, but do not prove a stop exists at that precise point today. The UI labels them as GTFS-listed and not field-verified. A static schedule does not supply vehicle positions, live ETAs, crowd levels, or passenger occupancy.

## Reimport

From the repository root, run the importer after replacing the locally saved ZIP with an authorized updated static feed:

```powershell
.\.venv\Scripts\python.exe scripts\process_gtfs.py
```

Inspect `outputs/gtfs_validation.json` and confirm `usable_for_scheduled_routing` is true before publishing the refreshed database.
