from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.database import connect, gtfs_is_usable
from app.schemas import StopDemandResponse, StopDetailResponse, StopListResponse, StopMapResponse

router = APIRouter(prefix="/stops", tags=["stops"])


@router.get("", response_model=StopListResponse)
def list_stops(
    q: str | None = Query(default=None, min_length=1),
    limit: int = Query(50, ge=1, le=5000),
    offset: Annotated[int, Query(ge=0)] = 0,
    source: Literal["auto", "gtfs", "etm"] = "auto",
) -> dict:
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="ETM has not been processed yet") from exc
    try:
        use_gtfs = source == "gtfs" or (source == "auto" and gtfs_is_usable(con))
        if use_gtfs and not gtfs_is_usable(con):
            raise HTTPException(status_code=503, detail="No validated GTFS feed is loaded")
        if use_gtfs:
            query = "SELECT stop_id, stop_name, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE) FROM gtfs_stops"
            params: list[object] = []
            if q:
                query += " WHERE lower(stop_name) LIKE ?"
                params.append(f"%{q.casefold()}%")
            query += " ORDER BY stop_name LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = con.execute(query, params).fetchall()
            return {
                "items": [
                    {
                        "id": row[0],
                        "stop_name": row[1],
                        "coordinates": {"latitude": row[2], "longitude": row[3]}
                        if row[2] is not None and row[3] is not None else None,
                        "demand_available": False,
                    }
                    for row in rows
                ],
                "source": "GTFS stop IDs; ETM match is not reviewed",
                "total_returned": len(rows),
                "offset": offset,
                "next_offset": offset + len(rows) if len(rows) == limit else None,
            }
        if q:
            rows = con.execute(
                "SELECT stop_id, stop_name FROM stop_catalog WHERE lower(stop_name) LIKE ? ORDER BY stop_name LIMIT ? OFFSET ?",
                [f"%{q.casefold()}%", limit, offset],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT stop_id, stop_name FROM stop_catalog ORDER BY stop_name LIMIT ? OFFSET ?", [limit, offset]
            ).fetchall()
        return {
            "items": [
                {"id": row[0], "stop_name": row[1], "coordinates": None, "demand_available": True}
                for row in rows
            ],
            "source": "ETM ticket start stop labels; not yet matched to GTFS stop IDs",
            "total_returned": len(rows),
            "offset": offset,
            "next_offset": offset + len(rows) if len(rows) == limit else None,
        }
    finally:
        con.close()


@router.get("/map", response_model=StopMapResponse)
def map_stops(
    south: float = Query(..., ge=-90, le=90),
    west: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    limit: int = Query(default=2000, ge=1, le=5000),
) -> dict:
    if south >= north or west >= east:
        raise HTTPException(status_code=422, detail="Map bounds must have south < north and west < east")
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Processed data is unavailable") from exc
    try:
        if not gtfs_is_usable(con):
            raise HTTPException(status_code=503, detail="Map stop coordinates require a validated GTFS feed")
        rows = con.execute(
            """
            SELECT stop_id, stop_name, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE)
            FROM gtfs_stops
            WHERE try_cast(stop_lat AS DOUBLE) BETWEEN ? AND ?
              AND try_cast(stop_lon AS DOUBLE) BETWEEN ? AND ?
            ORDER BY stop_name LIMIT ?
            """,
            [south, north, west, east, limit],
        ).fetchall()
        return {
            "items": [
                {
                    "id": row[0],
                    "stop_name": row[1],
                    "coordinates": {"latitude": row[2], "longitude": row[3]},
                    "demand_available": False,
                }
                for row in rows
            ],
            "source": "GTFS static stop coordinates; ETM matching has not been reviewed",
            "total_returned": len(rows),
        }
    finally:
        con.close()


@router.get("/{stop_id}/demand", response_model=StopDemandResponse)
def stop_demand(
    stop_id: str,
    route: str | None = None,
    day_of_week: int | None = Query(default=None, ge=0, le=6),
    transaction_hour: int | None = Query(default=None, ge=0, le=23),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="ETM has not been processed yet") from exc
    try:
        name_row = con.execute(
            "SELECT stop_name FROM stop_catalog WHERE stop_id = ? LIMIT 1", [stop_id]
        ).fetchone()
        if name_row is None:
            gtfs_exists = gtfs_is_usable(con)
            if gtfs_exists and con.execute("SELECT 1 FROM gtfs_stops WHERE stop_id = ? LIMIT 1", [stop_id]).fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="No reviewed ETM-to-GTFS stop match is available for this GTFS stop",
                )
            raise HTTPException(status_code=404, detail=f"Stop not found: {stop_id}")
        stop_name = name_row[0]
        clauses = ["stop_id = ?"]
        params: list[object] = [stop_id]
        if route is not None:
            clauses.append("route = ?")
            params.append(route)
        if day_of_week is not None:
            clauses.append("day_of_week = ?")
            params.append(day_of_week)
        if transaction_hour is not None:
            clauses.append("transaction_hour = ?")
            params.append(transaction_hour)
        if date_from is not None:
            clauses.append("service_date >= ?")
            params.append(date_from)
        if date_to is not None:
            clauses.append("service_date <= ?")
            params.append(date_to)
        where = " AND ".join(clauses)
        totals = con.execute(
            "SELECT coalesce(sum(passenger_volume), 0), coalesce(sum(transaction_count), 0), "
            "count(DISTINCT service_date) FROM stop_demand WHERE " + where,
            params,
        ).fetchone()
        total_observations = con.execute(
            "SELECT count(*) FROM stop_demand WHERE " + where, params
        ).fetchone()[0]
        rows = con.execute(
            "SELECT service_date, route, day_of_week, transaction_hour, passenger_volume, transaction_count "
            "FROM stop_demand WHERE " + where + " ORDER BY service_date, transaction_hour, route LIMIT ? OFFSET ?",
            [*params, limit + 1, offset],
        ).fetchall()
        observations = rows[:limit]
        return {
            "stop_name": stop_name,
            "stop_id": stop_id,
            "data_source": "October-Delhi ETM CSV",
            "prediction_type": "historical_ticket_start_volume",
            "status": "historical",
            "timestamp_basis": "ticket transaction time; not verified boarding time",
            "generated_at": datetime.now(UTC),
            "passenger_volume": totals[0],
            "transaction_count": totals[1],
            "days_covered": totals[2],
            "observation_count": len(observations),
            "observations_truncated": total_observations > limit,
            "total_observations": total_observations,
            "next_offset": offset + len(observations) if offset + len(observations) < total_observations else None,
            "confidence": "descriptive_observation",
            "confidence_note": "This is an aggregation of recorded ticket rows, not a waiting-queue or occupancy estimate.",
            "observations": [
                {
                    "date": row[0].isoformat(),
                    "route": row[1],
                    "day_of_week": row[2],
                    "transaction_hour": row[3],
                    "passenger_volume": row[4],
                    "transaction_count": row[5],
                }
                for row in observations
            ],
        }
    finally:
        con.close()


@router.get("/{stop_id}", response_model=StopDetailResponse)
def stop_detail(stop_id: str) -> dict:
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="ETM has not been processed yet") from exc
    try:
        if not stop_id.startswith("etm_"):
            gtfs_exists = gtfs_is_usable(con)
            if not gtfs_exists:
                raise HTTPException(status_code=404, detail=f"Stop not found: {stop_id}")
            gtfs = con.execute(
                "SELECT stop_id, stop_name, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE) "
                "FROM gtfs_stops WHERE stop_id = ?",
                [stop_id],
            ).fetchone()
            if gtfs is None:
                raise HTTPException(status_code=404, detail=f"Stop not found: {stop_id}")
            return {
                "id": gtfs[0],
                "stop_name": gtfs[1],
                "coordinates": {"latitude": gtfs[2], "longitude": gtfs[3]}
                if gtfs[2] is not None and gtfs[3] is not None else None,
                "data_source": "loaded GTFS; ticket demand match not reviewed",
                "first_observed_date": None,
                "last_observed_date": None,
                "passenger_volume": 0,
                "transaction_count": 0,
                "routes_observed": 0,
            }
        row = con.execute(
            """
            SELECT c.stop_id, c.stop_name, min(d.service_date), max(d.service_date),
                   coalesce(sum(d.passenger_volume), 0), coalesce(sum(d.transaction_count), 0),
                   count(DISTINCT d.route) FILTER (WHERE d.route IS NOT NULL)
            FROM stop_catalog c LEFT JOIN stop_demand d USING (stop_id)
            WHERE c.stop_id = ? GROUP BY c.stop_id, c.stop_name
            """,
            [stop_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Stop not found: {stop_id}")
        return {
            "id": row[0],
            "stop_name": row[1],
            "coordinates": None,
            "data_source": "October-Delhi ETM CSV",
            "first_observed_date": row[2],
            "last_observed_date": row[3],
            "passenger_volume": row[4],
            "transaction_count": row[5],
            "routes_observed": row[6],
        }
    finally:
        con.close()

