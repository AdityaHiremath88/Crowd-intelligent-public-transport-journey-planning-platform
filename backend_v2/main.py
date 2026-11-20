from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend_v2.config import CORS_ORIGINS, DATABASE_PATH
from backend_v2.routing import active_services_for_date, rank_journeys, search_journeys
from backend_v2.schedule import load_schedule_data
from backend_v2.schemas import JourneyLeg, JourneyOption, JourneySearchRequest, JourneySearchResponse, JourneyStop, RouteActivityObservation, RouteActivityResponse, StopItem, StopSearchResponse

app = FastAPI(
    title="Yuktix Backend v2",
    version="0.2.0",
    description=(
        "Versioned Yuktix bus journey-planning API. Schedule data is static; "
        "historical ticket activity is not physical crowding."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/api/v2/health", tags=["system"])
def health() -> dict:
    """Liveness check; does not require the GTFS database to be present."""
    return {"status": "ok", "service": "yuktix-backend-v2", "generated_at": datetime.now(UTC)}


@app.get("/api/v2/capabilities", tags=["system"])
def capabilities() -> dict:
    """Return feature availability without requiring an imported dataset."""
    tables: set[str] = set()
    if DATABASE_PATH.is_file():
        con = duckdb.connect(str(DATABASE_PATH), read_only=True)
        try:
            tables = {row[0] for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()}
        finally:
            con.close()
    schedule_available = False
    if "gtfs_import_metadata" in tables:
        con = duckdb.connect(str(DATABASE_PATH), read_only=True)
        try:
            row = con.execute(
                "SELECT usable_for_scheduled_routing FROM gtfs_import_metadata ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
            schedule_available = bool(row and row[0])
        finally:
            con.close()
    activity_available = "etm_route_activity" in tables and "etm_import_metadata" in tables
    return {
        "service": "yuktix-backend-v2",
        "scheduled_journey_search": schedule_available,
        "gtfs_stop_search": schedule_available,
        "historical_route_activity": activity_available,
        "physical_crowding_estimates": False,
        "live_vehicle_tracking": False,
    }


@app.get("/api/v2/ready", tags=["system"])
def readiness() -> dict:
    """Readiness check for a validated static GTFS import."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail={"code": "GTFS_DATABASE_MISSING", "message": "Run the v2 GTFS import first."},
        )
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        exists = con.execute(
            """SELECT count(*) FROM information_schema.tables
               WHERE table_schema='main' AND table_name='gtfs_import_metadata'"""
        ).fetchone()[0]
        if not exists:
            raise HTTPException(
                status_code=503,
                detail={"code": "GTFS_IMPORT_METADATA_MISSING", "message": "GTFS import metadata is missing."},
            )
        row = con.execute(
            """SELECT imported_at, source_file, source_sha256, usable_for_scheduled_routing,
                      service_start_date, service_end_date, row_counts_json, issues_json
               FROM gtfs_import_metadata ORDER BY imported_at DESC LIMIT 1"""
        ).fetchone()
        if row is None or not row[3]:
            raise HTTPException(
                status_code=503,
                detail={"code": "GTFS_NOT_ROUTABLE", "message": "Imported GTFS failed schedule checks."},
            )
        return {
            "status": "ready",
            "gtfs_available": True,
            "source_file": row[1],
            "source_sha256": row[2],
            "imported_at": row[0],
            "service_start_date": row[4],
            "service_end_date": row[5],
            "row_counts": json.loads(row[6]),
            "issues": json.loads(row[7]),
        }
    finally:
        con.close()


@app.get("/api/v2/routes/{route_id}/activity", response_model=RouteActivityResponse, tags=["historical activity"])
def route_activity(
    route_id: str,
    target_date: Annotated[date, Query(description="Local service date as YYYY-MM-DD")],
    hour: Annotated[int, Query(ge=0, le=23)],
) -> RouteActivityResponse:
    """Describe past ETM ticket activity comparable to a route, weekday, and hour."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail={"code": "GTFS_DATABASE_MISSING", "message": "Run the v2 GTFS import first."})
    service_date = target_date
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        tables = {row[0] for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()}
        if "etm_route_activity" not in tables or "etm_import_metadata" not in tables:
            raise HTTPException(status_code=503, detail={
                "code": "ETM_ACTIVITY_NOT_IMPORTED",
                "message": "Import the cleaned October ETM bundle before requesting historical route activity.",
            })
        route = con.execute(
            "SELECT route_id, coalesce(nullif(route_short_name, ''), route_long_name, route_id) FROM routes WHERE route_id = ?",
            [route_id],
        ).fetchone()
        if route is None:
            raise HTTPException(status_code=404, detail={"code": "UNKNOWN_ROUTE", "message": "Unknown GTFS route ID."})
        route_label = route[1]
        exact_short_name = con.execute(
            "SELECT route_short_name FROM routes WHERE route_id = ?", [route_id]
        ).fetchone()[0]
        observations = []
        label_candidate_exists = False
        if exact_short_name:
            label_candidate_exists = con.execute(
                "SELECT EXISTS(SELECT 1 FROM etm_route_activity WHERE route_label = ?)",
                [exact_short_name],
            ).fetchone()[0]
            observations = con.execute("""
                SELECT service_date, passenger_volume, transaction_count
                FROM etm_route_activity
                WHERE route_label = ? AND day_of_week = ? AND transaction_hour = ?
                  AND service_date < ?
                ORDER BY service_date DESC
            """, [exact_short_name, service_date.weekday(), hour, service_date]).fetchall()
        count = len(observations)
        average_volume = (sum(row[1] for row in observations) / count) if count else None
        average_transactions = (sum(row[2] for row in observations) / count) if count else None
        weekday = service_date.strftime("%A")
        status = "unavailable" if not label_candidate_exists else "available" if count >= 3 else "insufficient_history"
        metadata = con.execute(
            "SELECT json_extract_string(limitations_json, '$[0]'), json_extract_string(limitations_json, '$[1]'), json_extract_string(limitations_json, '$[2]'), json_extract_string(limitations_json, '$[3]') FROM etm_import_metadata ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        return RouteActivityResponse(
            route_id=route_id,
            route_label=route_label,
            target_date=service_date,
            transaction_hour=hour,
            weekday=weekday,
            status=status,
            comparable_day_count=count,
            average_passenger_volume=round(average_volume, 2) if average_volume is not None else None,
            average_transaction_count=round(average_transactions, 2) if average_transactions is not None else None,
            observations=[RouteActivityObservation(date=row[0], passenger_volume=row[1], transaction_count=row[2]) for row in observations],
            route_match_status="exact_label_candidate_unverified" if label_candidate_exists else "no_exact_label_candidate",
            limitations=[item for item in metadata if item] if metadata else [],
        )
    finally:
        con.close()


@app.get("/api/v2/stops", response_model=StopSearchResponse, tags=["stops"])
def search_stops(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StopSearchResponse:
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail={"code": "GTFS_DATABASE_MISSING", "message": "Run the v2 GTFS import first."})
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        ready = con.execute(
            "SELECT usable_for_scheduled_routing FROM gtfs_import_metadata ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        if not ready or not ready[0]:
            raise HTTPException(status_code=503, detail={"code": "GTFS_NOT_ROUTABLE", "message": "Imported GTFS failed schedule checks."})
        where = "WHERE strpos(lower(stop_name), lower(?)) > 0" if q else ""
        params: list[object] = [q] if q else []
        rows = con.execute(
            f"""SELECT stop_id, stop_name, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE)
                FROM stops {where} ORDER BY lower(stop_name), stop_id LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        items = [StopItem(
            stop_id=row[0], stop_name=row[1] or row[0],
            latitude=row[2], longitude=row[3],
        ) for row in rows]
        return StopSearchResponse(
            items=items, offset=offset, total_returned=len(items),
            next_offset=offset + len(items) if len(items) == limit else None,
        )
    finally:
        con.close()


@app.post("/api/v2/journeys/search", response_model=JourneySearchResponse, tags=["journeys"])
def journey_search(request: JourneySearchRequest) -> JourneySearchResponse:
    try:
        schedule = load_schedule_data()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail={"code": "GTFS_DATABASE_MISSING", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail={"code": "GTFS_NOT_ROUTABLE", "message": str(exc)}) from exc
    if request.origin_stop_id not in schedule.stop_names:
        raise HTTPException(status_code=404, detail={"code": "UNKNOWN_ORIGIN_STOP", "message": "Unknown GTFS origin stop ID."})
    if request.destination_stop_id not in schedule.stop_names:
        raise HTTPException(status_code=404, detail={"code": "UNKNOWN_DESTINATION_STOP", "message": "Unknown GTFS destination stop ID."})

    timezone = ZoneInfo(schedule.timezone)
    departure = request.departure_datetime
    departure = departure.replace(tzinfo=timezone) if departure.tzinfo is None else departure.astimezone(timezone)
    if schedule.service_start_date and schedule.service_end_date and not schedule.service_start_date <= departure.date() <= schedule.service_end_date:
        raise HTTPException(
            status_code=503,
            detail={"code": "GTFS_SERVICE_DATE_OUT_OF_RANGE",
                    "message": "The loaded static timetable does not cover this local service date.",
                    "service_start_date": schedule.service_start_date.isoformat(),
                    "service_end_date": schedule.service_end_date.isoformat()},
        )
    departure_seconds = departure.hour * 3600 + departure.minute * 60 + departure.second
    options = search_journeys(
        schedule.trips, request.origin_stop_id, request.destination_stop_id,
        departure_seconds, active_services_for_date(departure.date(), schedule.calendar_rows, schedule.exception_rows),
        max_transfers=request.max_transfers, search_index=schedule.search_index,
    )
    if departure_seconds < 6 * 3600:
        previous_date = departure.date() - timedelta(days=1)
        previous = search_journeys(
            schedule.trips, request.origin_stop_id, request.destination_stop_id,
            departure_seconds + 24 * 3600,
            active_services_for_date(previous_date, schedule.calendar_rows, schedule.exception_rows),
            max_transfers=request.max_transfers, search_index=schedule.search_index,
        )
        options.extend(
            replace(
                option,
                departure_seconds=option.departure_seconds - 24 * 3600,
                arrival_seconds=option.arrival_seconds - 24 * 3600,
                legs=tuple(replace(leg, departure_seconds=leg.departure_seconds - 24 * 3600,
                                   arrival_seconds=leg.arrival_seconds - 24 * 3600)
                           for leg in option.legs),
            )
            for option in previous
        )
    deduplicated = {
        (tuple(leg.trip_id for leg in option.legs), option.departure_seconds, option.arrival_seconds): option
        for option in options
    }
    ranked = rank_journeys(
        list(deduplicated.values()), request.preference, max_transfers=request.max_transfers,
        requested_departure_seconds=departure_seconds,
    )[:10]
    day_start = datetime.combine(departure.date(), time.min, tzinfo=timezone)
    as_datetime = lambda seconds: day_start + timedelta(seconds=seconds)
    response_options = []
    for option in ranked:
        legs = [JourneyLeg(
            trip_id=leg.trip_id,
            route_id=leg.route_id,
            route_name=schedule.route_labels.get(leg.route_id, leg.route_id),
            from_stop=JourneyStop(stop_id=leg.from_stop_id, stop_name=leg.from_stop_name),
            to_stop=JourneyStop(stop_id=leg.to_stop_id, stop_name=leg.to_stop_name),
            departure_datetime=as_datetime(leg.departure_seconds),
            arrival_datetime=as_datetime(leg.arrival_seconds),
            stop_sequence=list(leg.stop_sequence),
        ) for leg in option.legs]
        waiting_seconds = max(0, option.departure_seconds - departure_seconds)
        for previous_leg, next_leg in zip(option.legs, option.legs[1:]):
            waiting_seconds += max(0, next_leg.departure_seconds - previous_leg.arrival_seconds)
        response_options.append(JourneyOption(
            legs=legs,
            departure_datetime=as_datetime(option.departure_seconds),
            arrival_datetime=as_datetime(option.arrival_seconds),
            duration_seconds=option.duration_seconds,
            waiting_seconds=waiting_seconds,
            transfers=option.transfers,
            transfer_stops=list(option.transfer_stops),
            score=option.score,
            score_components=option.score_components,
        ))
    return JourneySearchResponse(
        options=response_options,
        origin_stop_id=request.origin_stop_id,
        destination_stop_id=request.destination_stop_id,
        preference=request.preference,
        generated_at=datetime.now(UTC),
        ranking_note=(
            "Crowd data is unavailable. Options are ranked using scheduled travel time and transfers; "
            "the comfort preference cannot optimize for crowd exposure yet."
        ),
        message=None if response_options else "No scheduled journey was found for this departure and service date.",
    )
