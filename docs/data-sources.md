# Data sources and provenance

## ETM/e-ticket records

- Source URL: [October Delhi ETM CSV ZIP](https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/October-Delhi.csv.zip)
- Retrieved: November 17, 2026
- Local files: `datasets/etm/raw/October-Delhi.csv.zip` and the extracted `October-Delhi.csv`
- Archive size: 66,145,093 bytes; extracted CSV size: 290,014,457 bytes
- Observed rows: 2,559,899; observed timestamp range: October 1–31, 2026 (Asia/Kolkata offset)
- Reported source fields: `passenger_count`, `amount`, `vehicle_number`, `ticket_type_id`, `start_stop_name`, `end_stop_name`, `route`, `created_at`, `is_ac`

The CSV itself is the evidence used for the observed schema and counts. `created_at` is treated only as a transaction timestamp. A source label such as `start_stop_name` is preserved in its original field and exposed as a ticket-start label pending confirmation of its exact business meaning.

## Static bus GTFS

- Requested source: [Delhi Transport Stack data services](https://delhi.transportstack.in/data-services)
- The supplied download endpoint returned HTTP 401 during this setup attempt.
- The public [Delhi Open Transit Data static page](https://otd.delhi.gov.in/data/static/) lists a bus static dataset and displays a last-updated date of June 20, 2024. Its download flow requests usage/purpose and contact information.
- The [official OTD GTFS documentation](https://otd.delhi.gov.in/documentation/) lists agency, calendar, stops, routes, trips and stop_times, and cautions that static stop times are rough estimates based on a constant-speed assumption.

The supplied archive is committed at `datasets/shareable/delhi_buses_static_gtfs_v1.zip`. Its contents were inspected and include `stop_times.txt`; its provenance and redistribution permission have not been independently confirmed. Copy it to `datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip` for local processing and run `python -m scripts.process_gtfs`.

## Alternative-source investigation (November 17, 2026)

- [Transitland's Delhi bus feed page](https://www.transit.land/data/feeds/f-delhi~bus) identifies the upstream license as the OTD terms, but its active GTFS snapshot was fetched on February 25, 2023 and covers service through January 1, 2024. The page reports that the latest upstream fetch failed with HTTP 404. This is too stale for current journey recommendations.
- Transitland documents that GTFS archive downloads are available only on eligible Transitland plans and only where upstream redistribution is allowed. No account, API key, or paid-plan access is configured here; no access controls were bypassed.
- [Where is my DTC](https://whereismydtc.in/data-sources) is an independent project that describes its source as publicly published DTC/OTD data, but the reviewed page is not itself a GTFS archive or an operator authorization. Its claimed derived data was not copied or scraped.

Accordingly, no alternative schedule feed was downloaded. An old schedule would make the planner look functional while returning out-of-date service; it is not used as current Delhi data or mixed into ETM outputs.

