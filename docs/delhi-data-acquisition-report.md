# Delhi bus data acquisition and evidence report

**Verified:** 17 November 2026 (Asia/Kolkata). This is a point-in-time access check. A web page listing a feed does not prove that its files were downloaded, licensed for reuse, or operationally current.

## Acquisition outcome

One new Delhi operator artifact was obtained: the current DTC all-route timetable PDF linked by the official DTC site. No GTFS ZIP, authorized real-time feed, vehicle capacity table, or APC output was obtained. The DTC PDF is retained locally only, outside application inputs. It is human-oriented source material and has not been converted into production routing tables.

| Publisher/source | Evidence and content | Freshness / coverage | Access and reuse | Actual local result |
|---|---|---|---|---|
| Delhi Open Transit Data (GNCTD DoT/IIIT-Delhi), [static portal](https://otd.delhi.gov.in/data/static/), [docs](https://otd.delhi.gov.in/documentation/), [terms](https://otd.delhi.gov.in/static/assets/terms-and-conditions.pdf) | Portal lists GTFS static stops/routes/trips/stop_times/calendar; reported counts are 3,464 stops, 543 routes, 16,562 trips and 378,324 stop-time rows. OTD explicitly warns schedule times are rough estimates generated from a constant-speed assumption. | Portal showed last update 20 June 2024. Stale for a November 2026 journey request absent a newer approved feed. | Static download asks for name, email, purpose and usage type; terms let DoT refuse. No credentials or user details were submitted. Reuse/redistribution rights were not established. RT VehiclePositions needs authorized key. | Not downloaded; no archive validation performed. |
| DTC official [services and timetable page](https://dtc.delhi.gov.in/dtc/services-and-time-table), [Nov 2026 master timetable PDF](https://dtc.delhi.gov.in/sites/default/files/DTC/dtc_all_time_table_nov_2026.pdf) | DTC page identifies “Current D.T.C. Time Table Nov-2026”; linked PDF is 427 pages and human-readable route timetable material. | Page last updated 17 Nov 2026; PDF metadata creation 10 Nov 2026. Covers the DTC timetable published there; completeness against all Delhi cluster services was not established. | Publicly linked download worked. No explicit open licence or redistribution permission found. Keep local/private pending rights review. | **Downloaded and validated as a PDF** at `datasets/gtfs/raw/dtc_all_time_table_nov_2026.pdf`; 1,345,071 bytes; SHA-256 `EBB15D52DA8D4180B94BE6EB392A0592C4CDA95DFAD91C1F935F98931E518DE4`; 427 pages; unencrypted. Not GTFS; not imported into journey planner. |
| DTC official [circulars](https://dtc.delhi.gov.in/dtc-circulars) | Route changes/extensions are published as notices. | Recent route notice observed 3 Nov 2026; older notices also present. | Public notices, but no common machine-readable canonical route feed or reuse licence discovered. | Pages inspected only; no route data extracted. |
| Delhi Transport Stack, [data services](https://delhi.transportstack.in/data-services), [terms](https://delhi.transportstack.in/termsofuse) | Catalogue lists Delhi Bus GTFS Static and GTFS-RT and Cluster GPS; DTC GPS marked “soon” on inspected catalogue. | The catalogue did not surface feed-specific `feed_info` or reliable current service dates during this check. | Terms require user identity and purpose and permit authority refusal; dataset-specific licence conditions apply. Previously supplied download endpoint returned HTTP 401. No bypass attempted. | No dataset downloaded. |
| Delhi OTD realtime, [access page](https://otd.delhi.gov.in/data/realtime/) | Documentation identifies VehiclePositions endpoint. No verified TripUpdates/vehicle feed captured in this project. | Update cadence and current Delhi feed coverage cannot be verified without authorized feed access. | Key/account required; access form requests identity/contact/purpose. | No request made with fabricated or third-party credentials. |
| DIMTS, [fleet management](https://dimts.in/fleet-management.aspx) and GNCTD Transport Department [BI/operations EOI](https://transport.delhi.gov.in/sites/default/files/circulars-orders/eoi_for_business_intelligence_tool_for_analytics_dashboard_for_bus_operations.pdf) | Official pages describe AVL/GPS and ETM/AFCS operational systems. EOI discusses data/integration needs; it is not a public data dump. | Operational system descriptions, not a feed freshness guarantee. | Internal/authorized operational access. | No AVL, AFCS or APC data acquired. |
| DTC / GNCTD [BMS RFP](https://dtc.delhi.gov.in/sites/default/files/DTC/tender/rfp_bms.pdf) | Procurement material describes planned master bus management system producing GTFS static/realtime from approved operational databases; data ownership/access is restricted to authorized systems. | Procurement publication is not proof that the planned feed is live or public. | Explicitly controlled operational data. | Document inspected; no dataset. |
| Government secondary statistics, [Delhi Economic Survey 2025–26](https://delhiplanning.delhi.gov.in/sites/default/files/2026-03/economic_survey_english_0.pdf) | Aggregate fleet and passenger context. Not a trip-level capacity/occupancy dataset. | Annual report; aggregate reference. | Public government report; cite figures only with page/definition when used. | Inspected; no machine-readable records imported. |
| OpenCity DTC metadata / derived community GTFS | Secondary catalog and community feed metadata were checked; OpenCity file request was blocked by a Cloudflare JavaScript challenge. Mobility Database/Transitland metadata showed an archive whose service period ended 1 Jan 2024. A third-party “2027 expiry” change does not refresh underlying times. | Old archive metadata is not current service evidence. | Underlying OTD/DoT terms and redistribution must be verified; no challenge bypass. | No file obtained; not used. |
| Project ETM export | October Delhi CSV: 2,559,899 rows; supplied file is locally processed and hash recorded in ETM data quality docs. | 1–31 Oct 2026 transaction dates. | Data-specific licence/authority permissions were not in the delivered schema. Keep private/local until confirmed. | Present locally; quality-processed. |

## Which fields are obtainable today?

| Data element | Public evidence | CrowdWise status |
|---|---|---|
| Stops and coordinates | OTD static GTFS describes stops; DTC PDF may contain stop names/route text but not a validated geospatial key | No authorized current GTFS in DuckDB. DTC PDF not geocoded. |
| Routes and ordered stops | OTD GTFS provides route/trip/stop_times structure; DTC PDF contains human-form route material | No current validated machine feed. |
| Timetables and service calendar | OTD GTFS files include times/calendar but stale and explicitly approximate; DTC Nov 2026 PDF has timetable information but no normalized feed/calendar | DTC document obtained, not route-planner input. |
| Vehicle positions / actual arrival times | OTD documents authorized VehiclePositions API; DTC/Stack systems are described in institutional material | No authorized access/key; no live feature. Actual arrivals are not the static timetable. |
| Vehicle capacities | No source with capacities by actual vehicle ID/model was obtained | Unknown; occupancy percent and capacity thresholds disabled. |
| APC boarding/alighting / measured load | Public reporting describes APC deployment/procurement intent; internal access only, no export | No actual count observations. Cannot validate load. |

## Alternative routing source decision

The DTC November 2026 PDF is fresher than the OTD static feed listing, but freshness alone is insufficient. A route planner needs stable route/trip/service IDs, ordered stops, dated service calendars and machine-readable departure/arrival times. The PDF does not provide those as a validated GTFS dataset and timetable pages may not define complete operating calendars or transfer rules. We do not scrape or hand-transcribe it into inferred services. The community archive is out of service date; the Transport Stack endpoint is authenticated. Therefore scheduled journey API remains unavailable until an authorized, validated feed with a suitable service-date window is supplied.

## Follow-up acquisition protocol

Request an authorized OTD/Stack feed through the legitimate account/project process. Preserve the archive unchanged; hash it; record publisher, retrieval time, license and approval; inspect `feed_info.txt`, service dates and every required GTFS file; validate and only enable query dates covered by the feed. Separately request permitted AVL/ETM/APC extract access with explicit timestamp semantics, stable vehicle/run IDs, field dictionary and privacy terms. Do not expose raw vehicle identifiers or passenger-level data through public APIs.

## Sources and standards

- [GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/)
- [GTFS Realtime reference](https://gtfs.org/documentation/realtime/reference/)
- [OTD documentation](https://otd.delhi.gov.in/documentation/)
- [DTC Nov 2026 timetable page](https://dtc.delhi.gov.in/dtc/services-and-time-table)
- [Delhi Stack catalogue](https://delhi.transportstack.in/data-services)


