from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query

from app.database import connect
from app.schemas import RouteListResponse, RouteProfileResponse

router = APIRouter(prefix="/routes", tags=["routes"])
DATA_SOURCE = "October-Delhi ETM CSV"


def _connection():
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="ETM has not been processed yet") from exc
    available = {
        row[0] for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    }
    if not {"route_demand", "route_stop_catalog", "stop_demand"}.issubset(available):
        con.close()
        raise HTTPException(status_code=503, detail="Route demand aggregates are unavailable; reprocess the ETM dataset")
    return con


@router.get("", response_model=RouteListResponse)
def list_routes(
    q: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    con = _connection()
    try:
        where = "WHERE d.route IS NOT NULL"
        params: list[object] = []
        if q:
            where += " AND lower(d.route) LIKE ?"
            params.append(f"%{q.casefold()}%")
        total = con.execute(
            f"SELECT count(*) FROM (SELECT d.route FROM route_demand d {where} GROUP BY d.route)", params
        ).fetchone()[0]
        rows = con.execute(
            f"""
            WITH agg AS (
                SELECT d.route, sum(d.passenger_volume)::BIGINT passenger_volume,
                       sum(d.transaction_count)::BIGINT transaction_count,
                       min(d.service_date) first_date, max(d.service_date) last_date
                FROM route_demand d {where} GROUP BY d.route
            ), labels AS (
                SELECT route, count(*)::INTEGER start_label_count
                FROM route_stop_catalog GROUP BY route
            )
            SELECT agg.route, agg.passenger_volume, agg.transaction_count,
                   coalesce(labels.start_label_count, 0), agg.first_date, agg.last_date
            FROM agg LEFT JOIN labels USING (route)
            ORDER BY agg.passenger_volume DESC, agg.route
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return {
            "data_source": DATA_SOURCE,
            "generated_at": datetime.now(UTC),
            "items": [
                {
                    "route_label": row[0], "passenger_volume": row[1], "transaction_count": row[2],
                    "start_label_count": row[3], "first_observed_date": row[4], "last_observed_date": row[5],
                }
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
        }
    finally:
        con.close()


@router.get("/profile", response_model=RouteProfileResponse)
def route_profile(
    route_label: str = Query(min_length=1),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    con = _connection()
    try:
        clauses = ["d.route = ?"]
        params: list[object] = [route_label]
        if date_from:
            clauses.append("d.service_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("d.service_date <= ?")
            params.append(date_to)
        where = " AND ".join(clauses)
        totals = con.execute(
            f"""SELECT min(d.service_date), max(d.service_date), sum(d.passenger_volume)::BIGINT,
                       sum(d.transaction_count)::BIGINT
                FROM route_demand d WHERE {where}""",
            params,
        ).fetchone()
        if totals[2] is None:
            raise HTTPException(status_code=404, detail=f"No historical ETM route label found: {route_label}")
        label_clauses = ["route = ?"]
        label_params: list[object] = [route_label]
        if date_from:
            label_clauses.append("service_date >= ?")
            label_params.append(date_from)
        if date_to:
            label_clauses.append("service_date <= ?")
            label_params.append(date_to)
        label_count = con.execute(
            "SELECT count(DISTINCT stop_id) FROM stop_demand WHERE " + " AND ".join(label_clauses),
            label_params,
        ).fetchone()[0]
        hourly = con.execute(
            f"""SELECT d.transaction_hour, sum(d.passenger_volume)::BIGINT, sum(d.transaction_count)::BIGINT,
                       count(DISTINCT d.service_date)::INTEGER
                FROM route_demand d WHERE {where} GROUP BY 1 ORDER BY 1""",
            params,
        ).fetchall()
        weekday = con.execute(
            f"""SELECT d.day_of_week, sum(d.passenger_volume)::BIGINT, sum(d.transaction_count)::BIGINT,
                       count(DISTINCT d.service_date)::INTEGER
                FROM route_demand d WHERE {where} GROUP BY 1 ORDER BY 1""",
            params,
        ).fetchall()
        return {
            "data_source": DATA_SOURCE,
            "generated_at": datetime.now(UTC),
            "route_label": route_label,
            "first_observed_date": totals[0], "last_observed_date": totals[1],
            "passenger_volume": totals[2], "transaction_count": totals[3], "start_label_count": label_count,
            "hourly_profile": [
                {"transaction_hour": row[0], "passenger_volume": row[1], "transaction_count": row[2], "observed_dates": row[3]}
                for row in hourly
            ],
            "weekday_profile": [
                {"day_of_week": row[0], "passenger_volume": row[1], "transaction_count": row[2], "observed_dates": row[3]}
                for row in weekday
            ],
        }
    finally:
        con.close()
