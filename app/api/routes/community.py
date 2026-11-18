from __future__ import annotations

import math
import sqlite3
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.config import CROWDWISE_GEOFENCE_RADIUS_METERS, PRESENCE_TTL_SECONDS
from app.database import connect, gtfs_is_usable
from app.schemas import (
    CommunityCrowdResponse, CommunityReportItem, CommunityReportsResponse,
    CrowdReportRequest, CrowdReportResponse, PresenceAggregateResponse,
    PresenceSignalRequest, PresenceSignalResponse,
    TicketActivityForecastResponse,
)
from app.services.community_store import (
    DuplicateSubmission, RateLimitExceeded, store, utc_now,
)
from app.services.crowd_service import aggregate_community_reports
from app.services.demand_forecast_service import forecast_ticket_activity

reports_router = APIRouter(prefix="/reports", tags=["community reports"])
crowding_router = APIRouter(prefix="/crowding", tags=["crowd intelligence"])
presence_router = APIRouter(prefix="/presence", tags=["opt-in presence"])


def _stop(stop_id: str) -> dict:
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Stop reference data is unavailable") from exc
    try:
        gtfs = gtfs_is_usable(con)
        if gtfs:
            row = con.execute(
                "SELECT stop_id, stop_name, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE) FROM gtfs_stops WHERE stop_id=?",
                [stop_id],
            ).fetchone()
            if row:
                return {"id": row[0], "name": row[1], "lat": row[2], "lon": row[3], "identity": "gtfs_stop_id"}
        row = con.execute("SELECT stop_name FROM stop_catalog WHERE stop_id=?", [stop_id]).fetchone()
        if row:
            return {"id": stop_id, "name": row[0], "lat": None, "lon": None, "identity": "unreviewed_etm_stop_label"}
        raise HTTPException(status_code=404, detail=f"Unknown stop identifier: {stop_id}")
    finally:
        con.close()


def _caller_keys(request: Request, client_token: str) -> tuple[str, str]:
    remote = request.client.host if request.client else "unknown"
    return (
        store.privacy_key(client_token, "", "client"),
        store.privacy_key(remote, "", "network"),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_observed_at(observed_at: datetime, now: datetime) -> datetime:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="observed_at must include a timezone offset")
    value = observed_at.astimezone(UTC)
    if value > now + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="observed_at cannot be more than five minutes in the future")
    if value < now - timedelta(minutes=10):
        raise HTTPException(status_code=422, detail="observed_at is too old; reports must describe a recent observation")
    return value


def _store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DuplicateSubmission):
        return HTTPException(status_code=409, detail="A recent submission from this anonymous client already exists for this stop")
    if isinstance(exc, RateLimitExceeded):
        return HTTPException(status_code=429, detail="Community signal rate limit exceeded")
    return HTTPException(status_code=503, detail="Community signal storage is temporarily unavailable")


@reports_router.post("/crowd", response_model=CrowdReportResponse, status_code=status.HTTP_201_CREATED)
def submit_crowd_report(
    payload: CrowdReportRequest, request: Request,
    client_token: str = Header(..., alias="X-CrowdWise-Client", min_length=16, max_length=128),
) -> CrowdReportResponse:
    now = _now()
    observed_at = _validate_observed_at(payload.observed_at, now)
    stop = _stop(payload.stop_id)
    if payload.route_id:
        try:
            con = connect()
            try:
                if gtfs_is_usable(con):
                    valid = con.execute("SELECT 1 FROM gtfs_routes WHERE route_id=?", [payload.route_id]).fetchone()
                else:
                    valid = con.execute("SELECT 1 FROM route_demand WHERE route=? LIMIT 1", [payload.route_id]).fetchone()
                if not valid:
                    raise HTTPException(status_code=422, detail="route_id is not present in the available route reference")
            finally:
                con.close()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="Route reference data is unavailable") from exc
    client_key, network_key = _caller_keys(request, client_token)
    try:
        result = store.submit_report(
            stop_id=stop["id"], stop_name=stop["name"], route_id=payload.route_id,
            category=payload.category, feedback_code=payload.feedback_code,
            observed_at=observed_at, reporter_key=client_key, network_key=network_key, now=now,
        )
    except (DuplicateSubmission, RateLimitExceeded, sqlite3.Error) as exc:
        raise _store_error(exc) from exc
    return CrowdReportResponse(
        report_id=result["report_id"], stop_id=stop["id"], stop_name=stop["name"],
        category=payload.category, observed_at=observed_at,
        created_at=datetime.fromisoformat(result["created_at"]),
        expires_at=datetime.fromisoformat(result["expires_at"]),
        stop_identity_status=stop["identity"],
    )


@reports_router.get("/stop/{stop_id}", response_model=CommunityReportsResponse)
def recent_crowd_reports(stop_id: str) -> CommunityReportsResponse:
    stop = _stop(stop_id)
    now = _now()
    try:
        rows = store.recent_reports(stop_id, now=now)
    except sqlite3.Error as exc:
        raise _store_error(exc) from exc
    items = [CommunityReportItem(**row) for row in rows]
    return CommunityReportsResponse(
        stop_id=stop_id,
        status="COMMUNITY_REPORTED" if items else "UNAVAILABLE",
        report_count=len(items), reports=items, generated_at=now,
        limitations=[
            "Reports are subjective categories, not measured headcounts.",
            "Reporter identities are not verified; repeated independent people cannot be guaranteed.",
            "Reports expire automatically and are not ETM or APC observations.",
        ],
    )


@crowding_router.get("/stop/{stop_id}", response_model=CommunityCrowdResponse)
def stop_crowding(stop_id: str) -> CommunityCrowdResponse:
    stop = _stop(stop_id)
    now = _now()
    try:
        rows = store.recent_reports(stop_id, now=now)
    except sqlite3.Error as exc:
        raise _store_error(exc) from exc
    return aggregate_community_reports(stop_id, stop["name"], rows, now=now)


@crowding_router.get("/prediction", response_model=TicketActivityForecastResponse)
def predict_ticket_activity(
    stop_id: str,
    target_date: date,
    hour: int = Query(ge=0, le=23),
) -> TicketActivityForecastResponse:
    return forecast_ticket_activity(stop_id=stop_id, target_date=target_date, target_hour=hour)


def _distance_meters(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius = 6_371_000.0
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lam = math.radians(lon_b - lon_a)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lam / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(value)))


@presence_router.post("/signals", response_model=PresenceSignalResponse, status_code=status.HTTP_201_CREATED)
def submit_presence_signal(
    payload: PresenceSignalRequest, request: Request,
    client_token: str = Header(..., alias="X-CrowdWise-Client", min_length=16, max_length=128),
) -> PresenceSignalResponse:
    stop = _stop(payload.stop_id)
    if stop["identity"] != "gtfs_stop_id" or stop["lat"] is None or stop["lon"] is None:
        raise HTTPException(status_code=503, detail="Opt-in geofence signals require a validated GTFS stop with coordinates")
    if payload.accuracy_meters > CROWDWISE_GEOFENCE_RADIUS_METERS:
        raise HTTPException(status_code=422, detail="Reported location accuracy is too coarse for the configured geofence")
    distance = _distance_meters(payload.latitude, payload.longitude, stop["lat"], stop["lon"])
    if distance > CROWDWISE_GEOFENCE_RADIUS_METERS + payload.accuracy_meters:
        raise HTTPException(status_code=422, detail="Location is outside the stop geofence")
    now = _now()
    client_key, network_key = _caller_keys(request, client_token)
    try:
        result = store.submit_presence(
            stop_id=stop["id"], participant_key=client_key, network_key=network_key, now=now
        )
    except (DuplicateSubmission, RateLimitExceeded, sqlite3.Error) as exc:
        raise _store_error(exc) from exc
    return PresenceSignalResponse(
        signal_id=result["signal_id"], stop_id=stop["id"],
        created_at=datetime.fromisoformat(result["created_at"]),
        expires_at=datetime.fromisoformat(result["expires_at"]), status="ACCEPTED",
        storage_note="Precise coordinates were used only for geofence validation and were not stored.",
    )


@presence_router.get("/stops/{stop_id}", response_model=PresenceAggregateResponse)
def stop_presence(stop_id: str) -> PresenceAggregateResponse:
    stop = _stop(stop_id)
    now = _now()
    try:
        count = store.presence_count(stop_id, now=now)
    except sqlite3.Error as exc:
        raise _store_error(exc) from exc
    return PresenceAggregateResponse(
        stop_id=stop["id"], status="COMMUNITY_REPORTED" if count else "UNAVAILABLE",
        signal_count=count, generated_at=now, expires_after_seconds=PRESENCE_TTL_SECONDS,
        limitations=[
            "Count is active pseudonymous opted-in signals, not all commuters or people waiting.",
            "A signal is not proof of a unique person; shared devices and changing network identifiers are possible.",
            "No exact coordinates or location history are exposed or retained.",
        ],
    )
