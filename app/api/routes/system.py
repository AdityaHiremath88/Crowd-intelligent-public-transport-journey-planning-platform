from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.database import connect, gtfs_is_usable
from app.config import GTFS_RT_URL
from app.schemas import (
    DatasetCatalogEntry,
    DatasetCatalogResponse,
    MethodologyResponse,
    SystemCapabilitiesResponse,
)
from app.services.community_store import store as community_store
from app.services.realtime_service import current_snapshot

router = APIRouter(prefix="/system", tags=["system"])
ETM_CORE_TABLES = {"etm_records", "stop_catalog", "stop_demand", "data_quality"}


def _tables(con) -> set[str]:
    return {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    }


@router.get("/capabilities", response_model=SystemCapabilitiesResponse)
def capabilities() -> SystemCapabilitiesResponse:
    try:
        con = connect()
    except FileNotFoundError:
        tables = set()
    else:
        try:
            tables = _tables(con)
            usable_gtfs = gtfs_is_usable(con)
            map_row = con.execute("SELECT usable_for_map FROM gtfs_quality LIMIT 1").fetchone() if "gtfs_quality" in tables else None
            gtfs_map_available = bool(map_row and str(map_row[0]).lower() in {"true", "1"})
        finally:
            con.close()
    if not tables:
        usable_gtfs = False
        gtfs_map_available = False
    etm_available = ETM_CORE_TABLES.issubset(tables)
    return SystemCapabilitiesResponse(
        generated_at=datetime.now(UTC),
        historical_ticket_analytics=etm_available,
        gtfs_stop_catalog=usable_gtfs,
        gtfs_map_coordinates=gtfs_map_available,
        scheduled_journey_search=usable_gtfs,
        trip_level_load_estimation=False,
        crowd_classification=False,
        live_vehicle_positions=current_snapshot()[0]["status"] == "HEALTHY",
        live_vehicle_feed_configured=bool(GTFS_RT_URL),
        community_reporting=True,
        opt_in_presence=gtfs_map_available,
        historical_ticket_activity_forecast=etm_available,
        explanation=[
            "ETM analytics describe ticket records by transaction timestamp; they are not measured waiting queues.",
            "Segment loads are unavailable because ticket rows lack validated trip assignments and verified boarding/alighting events.",
            "Crowd labels are unavailable because ticketed load is not validated physical occupancy and vehicle capacity is not verified.",
            "GTFS schedule routing is enabled only when a feed passed import quality checks; static timetable time is approximate, not live.",
            "No authorized real-time vehicle feed is configured.",
            "Community crowd reports are subjective categories and do not establish unique reporters or measured counts.",
            "Opt-in presence signals require a validated GTFS stop with coordinates; only short-lived aggregates are exposed.",
            ("A persistent report HMAC key is available from configuration or a local ignored sidecar file." if community_store.secret_is_persistent else "Report deduplication key is not persistent; configure CROWDWISE_REPORT_HMAC_SECRET for stable deduplication across restarts."),
        ],
    )


@router.get("/datasets", response_model=DatasetCatalogResponse)
def datasets() -> DatasetCatalogResponse:
    try:
        con = connect()
    except FileNotFoundError:
        return DatasetCatalogResponse(generated_at=datetime.now(UTC), datasets=[])
    try:
        tables = _tables(con)
        entries: list[DatasetCatalogEntry] = []
        if "data_quality" in tables:
            quality_rows = con.execute("SELECT * FROM data_quality WHERE dataset_name='etm' LIMIT 1").fetchall()
            columns = [column[0] for column in con.description]
            if quality_rows:
                row = dict(zip(columns, quality_rows[0], strict=True))
                entries.append(DatasetCatalogEntry(
                    dataset_name="etm",
                    status="processed",
                    source_file=row.get("source_file"),
                    source_sha256=row.get("source_sha256"),
                    source_size_bytes=row.get("source_size_bytes"),
                    generated_at=row.get("generated_at"),
                    schema_version=row.get("schema_version"),
                    pipeline_version=row.get("pipeline_version"),
                    input_rows=row.get("dataset_rows"),
                    retained_rows=row.get("retained_rows"),
                    excluded_rows=row.get("excluded_rows"),
                    first_observed=row.get("dataset_min_timestamp"),
                    last_observed=row.get("dataset_max_timestamp"),
                ))
        if "gtfs_quality" in tables:
            quality_rows = con.execute("SELECT * FROM gtfs_quality LIMIT 1").fetchall()
            columns = [column[0] for column in con.description]
            if quality_rows:
                row = dict(zip(columns, quality_rows[0], strict=True))
                entries.append(DatasetCatalogEntry(
                    dataset_name="gtfs",
                    status="processed" if str(row.get("usable_for_scheduled_routing")).lower() in {"true", "1"} else "invalid",
                    source_file=row.get("source_file"),
                    source_sha256=row.get("source_sha256"),
                    source_size_bytes=row.get("source_size_bytes"),
                    generated_at=row.get("generated_at"),
                    schema_version=row.get("schema_version"),
                    pipeline_version=row.get("pipeline_version"),
                    input_rows=row.get("total_rows"),
                    retained_rows=row.get("usable_stop_times"),
                    excluded_rows=row.get("invalid_rows"),
                    first_observed=row.get("service_start_date"),
                    last_observed=row.get("service_end_date"),
                ))
        return DatasetCatalogResponse(generated_at=datetime.now(UTC), datasets=entries)
    finally:
        con.close()


@router.get("/methodology", response_model=MethodologyResponse)
def methodology() -> MethodologyResponse:
    return MethodologyResponse(
        generated_at=datetime.now(UTC),
        historical_demand=(
            "Historical ticket activity grouped by normalized ETM start-stop label, source route label, "
            "transaction-local date/hour and weekday. Passenger volume is SUM(passenger_count); "
            "ticket transaction count is COUNT(*). Neither is a physical queue count."
        ),
        segment_load=(
            "Unavailable for the current ETM file. A future ticketed-load proxy may sum validated "
            "passenger journeys that cover a segment of one validated trip; it is not measured occupancy."
        ),
        crowd_categories=(
            "Unavailable. Capacity bands require verified vehicle capacity and calibrated thresholds; "
            "relative bands require comparable historical calibration and must not be described as occupancy percentages."
        ),
        journey_routing=(
            "When a quality-approved static GTFS feed is loaded, bounded timetable search evaluates scheduled journeys "
            "with up to three transfers using active calendar services and ordered stop times. A 300-second transfer "
            "buffer is assumed; GTFS transfer rules, walking paths and frequency trips are unsupported. "
            "Requested local service dates outside the loaded calendar window are rejected. Static Delhi timetable times are approximate."
        ),
        confidence=(
            "No passenger-load confidence score is currently published. A future assessment must include independent "
            "service-day coverage, stop/route matching, trip identity, comparable-day consistency and freshness; "
            "raw transaction count alone is insufficient."
        ),
    )
