from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
import sqlite3
from typing import Annotated
from zoneinfo import ZoneInfo

import duckdb
from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

from backend_v2.config import CORS_ORIGINS, DATABASE_PATH
from backend_v2.fares import estimate_leg_fare, summarize_journey_fares
from backend_v2.routing import active_services_for_date, rank_journeys, search_journeys
from backend_v2.schedule import load_schedule_data
from backend_v2.schemas import JourneyLeg, JourneyOption, JourneySearchRequest, JourneySearchResponse, JourneyStop, RouteActivityObservation, RouteActivityResponse, StopItem, StopSearchResponse
from app.schemas import CrowdReportRequest, CrowdReportResponse, CommunityReportsResponse, CommunityReportItem, CommunityCrowdResponse
from app.services.community_store import DuplicateSubmission, RateLimitExceeded, store, utc_now
from app.services.crowd_service import aggregate_community_reports

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
    allow_headers=["Content-Type", "Authorization", "X-CrowdWise-Client"],
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
        "estimated_fares": "dtc_fare_stage_stops" in tables,
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


def _community_stop(stop_id: str) -> dict:
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail={"code": "GTFS_DATABASE_MISSING", "message": "Stop reporting requires the GTFS import."})
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        row = con.execute("SELECT stop_id, stop_name FROM stops WHERE stop_id = ?", [stop_id]).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "UNKNOWN_STOP", "message": "Select a stop from the Delhi GTFS list."})
        return {"stop_id": row[0], "stop_name": row[1] or row[0]}
    finally:
        con.close()


def _community_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DuplicateSubmission):
        return HTTPException(status_code=409, detail={"code": "DUPLICATE_REPORT", "message": "A recent report from this app is already active for this stop."})
    if isinstance(exc, RateLimitExceeded):
        return HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "Too many reports. Please try again later."})
    return HTTPException(status_code=503, detail={"code": "COMMUNITY_STORE_UNAVAILABLE", "message": "Crowd reports are temporarily unavailable."})


@app.post("/api/v2/reports/crowd", response_model=CrowdReportResponse, status_code=status.HTTP_201_CREATED, tags=["community reports"])
def submit_crowd_report(
    payload: CrowdReportRequest,
    request: Request,
    client_token: str = Header(..., alias="X-CrowdWise-Client", min_length=16, max_length=128),
) -> CrowdReportResponse:
    now = utc_now()
    if payload.observed_at.tzinfo is None or payload.observed_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail={"code": "TIMEZONE_REQUIRED", "message": "Observation time must include a timezone."})
    observed_at = payload.observed_at.astimezone(UTC)
    if observed_at > now + timedelta(minutes=5) or observed_at < now - timedelta(minutes=10):
        raise HTTPException(status_code=422, detail={"code": "OBSERVATION_TIME_INVALID", "message": "Reports must describe a crowd observation from the last ten minutes."})
    stop = _community_stop(payload.stop_id)
    if payload.route_id:
        con = duckdb.connect(str(DATABASE_PATH), read_only=True)
        try:
            if not con.execute("SELECT 1 FROM routes WHERE route_id = ?", [payload.route_id]).fetchone():
                raise HTTPException(status_code=422, detail={"code": "UNKNOWN_ROUTE", "message": "Select a route from the GTFS route list."})
        finally:
            con.close()
    remote = request.client.host if request.client else "unknown"
    client_key = store.privacy_key(client_token, "", "client")
    network_key = store.privacy_key(remote, "", "network")
    try:
        result = store.submit_report(
            stop_id=stop["stop_id"], stop_name=stop["stop_name"], route_id=payload.route_id,
            category=payload.category, feedback_code=payload.feedback_code,
            observed_at=observed_at, reporter_key=client_key, network_key=network_key, now=now,
        )
    except (DuplicateSubmission, RateLimitExceeded, sqlite3.Error) as exc:
        raise _community_error(exc) from exc
    return CrowdReportResponse(
        report_id=result["report_id"], stop_id=stop["stop_id"], stop_name=stop["stop_name"],
        category=payload.category, observed_at=observed_at,
        created_at=datetime.fromisoformat(result["created_at"]),
        expires_at=datetime.fromisoformat(result["expires_at"]),
        stop_identity_status="gtfs_stop_id",
    )


@app.get("/api/v2/reports/stop/{stop_id}", response_model=CommunityReportsResponse, tags=["community reports"])
def recent_crowd_reports(stop_id: str) -> CommunityReportsResponse:
    _community_stop(stop_id)
    now = utc_now()
    try:
        rows = store.recent_reports(stop_id, now=now)
    except sqlite3.Error as exc:
        raise _community_error(exc) from exc
    items = [CommunityReportItem(**row) for row in rows]
    return CommunityReportsResponse(
        stop_id=stop_id, status="COMMUNITY_REPORTED" if items else "UNAVAILABLE",
        report_count=len(items), reports=items, generated_at=now,
        limitations=["Reports are subjective categories, not measured headcounts.", "Reports expire automatically and do not represent bus occupancy."],
    )


@app.get("/api/v2/crowding/stop/{stop_id}", response_model=CommunityCrowdResponse, tags=["community reports"])
def stop_crowding(stop_id: str) -> CommunityCrowdResponse:
    stop = _community_stop(stop_id)
    now = utc_now()
    try:
        rows = store.recent_reports(stop_id, now=now)
    except sqlite3.Error as exc:
        raise _community_error(exc) from exc
    return aggregate_community_reports(stop_id, stop["stop_name"], rows, now=now)


@app.get("/api/v2/routes", tags=["routes"])
def search_routes(q: str = Query(min_length=1, max_length=80), limit: int = Query(default=12, ge=1, le=30)) -> dict:
    """Search route numbers and names from the imported static GTFS feed."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail={"code": "GTFS_DATABASE_MISSING", "message": "Run the v2 GTFS import first."})
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT r.route_id, coalesce(nullif(r.route_short_name, ''), r.route_id),
                   coalesce(r.route_long_name, ''), count(DISTINCT t.trip_id)
            FROM routes r JOIN trips t USING(route_id)
            WHERE lower(coalesce(r.route_short_name, '') || ' ' || coalesce(r.route_long_name, '')) LIKE '%' || lower(?) || '%'
            GROUP BY r.route_id, r.route_short_name, r.route_long_name
            ORDER BY CASE WHEN lower(coalesce(r.route_short_name, '')) = lower(?) THEN 0 ELSE 1 END,
                     lower(coalesce(r.route_short_name, '')), r.route_id
            LIMIT ?
        """, [q.strip(), q.strip(), limit]).fetchall()
        return {"items": [{"route_id": row[0], "route_name": row[1], "route_long_name": row[2], "scheduled_trip_count": row[3]} for row in rows], "source": "GTFS static feed"}
    finally:
        con.close()


@app.get("/api/v2/routes/{route_id}", tags=["routes"])
def route_detail(route_id: str) -> dict:
    """Return one representative ordered stop pattern for a GTFS route."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail={"code": "GTFS_DATABASE_MISSING", "message": "Run the v2 GTFS import first."})
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        route = con.execute("SELECT route_id, coalesce(nullif(route_short_name, ''), route_id), coalesce(route_long_name, '') FROM routes WHERE route_id = ?", [route_id]).fetchone()
        if not route:
            raise HTTPException(status_code=404, detail={"code": "UNKNOWN_ROUTE", "message": "Unknown GTFS route ID."})
        trip = con.execute("""
            SELECT t.trip_id, coalesce(t.trip_headsign, '') FROM trips t JOIN stop_times st USING(trip_id)
            WHERE t.route_id = ? GROUP BY t.trip_id, t.trip_headsign ORDER BY count(*) DESC, t.trip_id LIMIT 1
        """, [route_id]).fetchone()
        if not trip:
            raise HTTPException(status_code=404, detail={"code": "ROUTE_WITHOUT_TRIPS", "message": "No scheduled trips were found for this route."})
        stops = con.execute("""
            SELECT s.stop_id, s.stop_name FROM stop_times st JOIN stops s USING(stop_id)
            WHERE st.trip_id = ? ORDER BY try_cast(st.stop_sequence AS INTEGER), st.stop_sequence
        """, [trip[0]]).fetchall()
        return {"route_id": route[0], "route_name": route[1], "route_long_name": route[2], "headsign": trip[1], "stops": [{"stop_id": row[0], "stop_name": row[1]} for row in stops], "source": "GTFS static feed", "pattern_note": "Stops follow one representative scheduled trip pattern; order can vary on other trips."}
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
    if request.route_id:
        if not any(trip.route_id == request.route_id for trip in schedule.trips):
            raise HTTPException(status_code=404, detail={"code": "UNKNOWN_ROUTE", "message": "Unknown GTFS route ID."})
        options = [option for option in options if any(leg.route_id == request.route_id for leg in option.legs)]
    if departure_seconds < 6 * 3600:
        previous_date = departure.date() - timedelta(days=1)
        previous = search_journeys(
            schedule.trips, request.origin_stop_id, request.destination_stop_id,
            departure_seconds + 24 * 3600,
            active_services_for_date(previous_date, schedule.calendar_rows, schedule.exception_rows),
            max_transfers=request.max_transfers, search_index=schedule.search_index,
        )
        if request.route_id:
            previous = [option for option in previous if any(leg.route_id == request.route_id for leg in option.legs)]
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
        legs = []
        fare_estimates = []
        for leg in option.legs:
            path_names = [schedule.stop_names.get(stop_id, stop_id) for stop_id in leg.stop_sequence]
            fare_estimate = estimate_leg_fare(
                route_short_name=schedule.route_short_names.get(leg.route_id, ""),
                stop_names=path_names,
                database_path=DATABASE_PATH,
            )
            fare_estimates.append(fare_estimate)
            legs.append(JourneyLeg(
                trip_id=leg.trip_id,
                route_id=leg.route_id,
                route_name=schedule.route_labels.get(leg.route_id, leg.route_id),
                from_stop=JourneyStop(stop_id=leg.from_stop_id, stop_name=leg.from_stop_name),
                to_stop=JourneyStop(stop_id=leg.to_stop_id, stop_name=leg.to_stop_name),
                departure_datetime=as_datetime(leg.departure_seconds),
                arrival_datetime=as_datetime(leg.arrival_seconds),
                stop_sequence=list(leg.stop_sequence),
                fare_estimate=fare_estimate,
            ))
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
            fare_estimate=summarize_journey_fares(fare_estimates),
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
        message=None if response_options else ("No scheduled journey using this route was found for the selected stops and departure time." if request.route_id else "No scheduled journey was found for this departure and service date."),
    )
