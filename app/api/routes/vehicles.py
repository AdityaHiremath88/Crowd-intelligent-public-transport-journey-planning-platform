from __future__ import annotations

from datetime import UTC, datetime
from app.config import GTFS_RT_MAX_STALENESS_SECONDS

from fastapi import APIRouter, HTTPException

from app.database import connect, gtfs_is_usable
from app.schemas import RealtimeStatusResponse, VehicleListResponse, VehiclePositionResponse
from app.services.realtime_service import DATA_SOURCE, current_snapshot

vehicles_router = APIRouter(prefix="/vehicles", tags=["live vehicles"])
realtime_router = APIRouter(prefix="/realtime", tags=["live feed"])


def _as_datetime(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value is not None else None


def _status_response(raw: dict) -> RealtimeStatusResponse:
    state = raw["status"]
    current_count = raw.get("current_vehicle_count", 0) if state == "HEALTHY" else 0
    stale_count = raw.get("stale_vehicle_count", 0)
    if state in {"STALE", "ERROR", "NOT_CONFIGURED"}:
        stale_count = max(stale_count, raw.get("current_vehicle_count", 0))
    return RealtimeStatusResponse(
        status=state, configured=raw["configured"], authorized=raw["authorized"],
        last_attempt_at=_as_datetime(raw.get("last_attempt_at")),
        last_success_at=_as_datetime(raw.get("last_success_at")),
        feed_timestamp=_as_datetime(raw.get("feed_timestamp")),
        current_vehicle_count=current_count,
        stale_vehicle_count=stale_count,
        last_error_code=raw.get("last_error_code"), generated_at=datetime.now(UTC),
        data_source=DATA_SOURCE,
    )


def _vehicle_response(row: dict) -> VehiclePositionResponse:
    now = int(datetime.now(UTC).timestamp())
    return VehiclePositionResponse(
        vehicle_id=row["vehicle_id"], trip_id=row.get("trip_id"), route_id=row.get("route_id"),
        route_id_match_status="VERIFIED_STATIC_GTFS" if row.get("route_id_matched") else "PROVIDER_ID_ONLY",
        latitude=row["latitude"], longitude=row["longitude"], bearing=row.get("bearing"),
        speed_meters_per_second=row.get("speed_mps"), current_stop_id=row.get("current_stop_id"),
        current_stop_sequence=row.get("current_stop_sequence"), current_status=row.get("current_status"),
        position_timestamp=datetime.fromtimestamp(row["position_timestamp"], UTC),
        feed_timestamp=_as_datetime(row.get("feed_timestamp")),
        freshness_seconds=max(0, now - row["position_timestamp"]),
        status=("LIVE_OBSERVED" if now - row["position_timestamp"] <= GTFS_RT_MAX_STALENESS_SECONDS else "STALE_CACHED"),
        data_source=DATA_SOURCE,
    )


@realtime_router.get("/status", response_model=RealtimeStatusResponse)
def realtime_status() -> RealtimeStatusResponse:
    return _status_response(current_snapshot()[0])


@vehicles_router.get("/live", response_model=VehicleListResponse)
def live_vehicles() -> VehicleListResponse:
    state, raw_vehicles = current_snapshot()
    return VehicleListResponse(
        status=state["status"], generated_at=datetime.now(UTC),
        last_success_at=_as_datetime(state.get("last_success_at")),
        vehicles=[_vehicle_response(item) for item in raw_vehicles], data_source=DATA_SOURCE,
    )


@vehicles_router.get("/buses/live", response_model=VehicleListResponse)
def live_buses_compat() -> VehicleListResponse:
    """Frontend-friendly alias for the Delhi live positions feed."""
    return live_vehicles()


@vehicles_router.get("/route/{route_id}", response_model=VehicleListResponse)
def route_vehicles(route_id: str) -> VehicleListResponse:
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Validated GTFS is unavailable") from exc
    try:
        if not gtfs_is_usable(con):
            raise HTTPException(status_code=503, detail="Live vehicle route matching requires validated GTFS")
        if not con.execute("SELECT 1 FROM gtfs_routes WHERE route_id=?", [route_id]).fetchone():
            raise HTTPException(status_code=404, detail=f"Unknown GTFS route: {route_id}")
    finally:
        con.close()
    state, raw_vehicles = current_snapshot()
    filtered = [row for row in raw_vehicles if row.get("route_id") == route_id]
    return VehicleListResponse(
        status=state["status"], generated_at=datetime.now(UTC),
        last_success_at=_as_datetime(state.get("last_success_at")),
        vehicles=[_vehicle_response(item) for item in filtered], data_source=DATA_SOURCE,
    )


@vehicles_router.get("/{vehicle_id}", response_model=VehiclePositionResponse)
def vehicle_detail(vehicle_id: str) -> VehiclePositionResponse:
    state, raw_vehicles = current_snapshot()
    if state["status"] != "HEALTHY":
        raise HTTPException(status_code=503, detail={"code": "REALTIME_UNAVAILABLE", "status": state["status"]})
    for row in raw_vehicles:
        if row["vehicle_id"] == vehicle_id:
            return _vehicle_response(row)
    raise HTTPException(status_code=404, detail=f"No current vehicle position for identifier: {vehicle_id}")


@vehicles_router.get("/{vehicle_id}/eta")
def vehicle_eta_unavailable(vehicle_id: str) -> dict:
    state, vehicles = current_snapshot()
    if state["status"] != "HEALTHY":
        raise HTTPException(status_code=503, detail={"code": "REALTIME_UNAVAILABLE", "status": state["status"]})
    if not any(row["vehicle_id"] == vehicle_id for row in vehicles):
        raise HTTPException(status_code=404, detail=f"No current vehicle position for identifier: {vehicle_id}")
    raise HTTPException(
        status_code=503,
        detail={
            "code": "ETA_UNAVAILABLE",
            "message": "Vehicle position alone does not support a validated stop ETA; an authorized TripUpdates feed or validated travel-time model is required.",
        },
    )
