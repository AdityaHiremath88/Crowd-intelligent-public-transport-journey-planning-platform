from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.database import connect
from app.schemas import (
    AnalyticsSeriesResponse,
    CorridorResponse,
    OverviewResponse,
    PeakHoursResponse,
    ServiceProfileResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
DATA_SOURCE = "October-Delhi ETM CSV"


def _connection():
    try:
        return connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="ETM has not been processed yet") from exc


@router.get("/overview", response_model=OverviewResponse)
def overview() -> dict:
    con = _connection()
    try:
        row = con.execute(
            """
            SELECT dataset_rows, retained_rows, excluded_rows, dataset_min_timestamp,
                   dataset_max_timestamp, generated_at, distinct_routes, distinct_vehicles,
                   distinct_start_stops, distinct_end_stops, null_vehicle_rows,
                   invalid_passenger_rows, exact_duplicate_rows, passenger_volume_total,
                   passenger_count_mean, null_start_stop_rows, null_end_stop_rows,
                   null_route_rows
            FROM data_quality WHERE dataset_name='etm'
            """
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=503, detail="ETM quality summary is missing")
        keys = [item[0] for item in con.description]
        result = dict(zip(keys, row, strict=True))
        result.update(
            data_source=DATA_SOURCE,
            data_status="historical",
            prediction_type="data_quality_overview",
            occupancy_predictions="unavailable",
            caveat=(
                "created_at is transaction time. ETM stop labels and vehicle numbers do not "
                "identify a complete individual bus trip or verified onboard load."
            ),
        )
        return result
    finally:
        con.close()


@router.get("/trends", response_model=AnalyticsSeriesResponse)
def trends(
    granularity: Literal["day", "week"] = "day",
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    con = _connection()
    try:
        clauses: list[str] = []
        params: list[object] = []
        if date_from:
            clauses.append("service_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("service_date <= ?")
            params.append(date_to)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        period_expr = "service_date" if granularity == "day" else "date_trunc('week', service_date)::DATE"
        rows = con.execute(
            f"""
            SELECT {period_expr} AS period, sum(passenger_volume)::BIGINT,
                   sum(transaction_count)::BIGINT
            FROM daily_demand{where}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        ).fetchall()
        return {
            "data_source": DATA_SOURCE,
            "generated_at": datetime.now(UTC),
            "points": [
                {"period": row[0].isoformat(), "passenger_volume": row[1], "transaction_count": row[2]}
                for row in rows
            ],
        }
    finally:
        con.close()


@router.get("/peak-hours", response_model=PeakHoursResponse)
def peak_hours(day_type: Literal["all", "weekday", "weekend"] = "all") -> dict:
    con = _connection()
    try:
        filter_sql = {
            "all": "TRUE",
            "weekday": "dayofweek(service_date) BETWEEN 1 AND 5",
            "weekend": "dayofweek(service_date) IN (0, 6)",
        }[day_type]
        rows = con.execute(
            f"""
            SELECT transaction_hour,
                   sum(passenger_volume)::BIGINT AS passenger_volume,
                   sum(transaction_count)::BIGINT AS transaction_count,
                   count(DISTINCT service_date)::INTEGER AS observed_dates
            FROM hourly_demand
            WHERE {filter_sql}
            GROUP BY 1 ORDER BY passenger_volume DESC
            """
        ).fetchall()
        return {
            "data_source": DATA_SOURCE,
            "day_type": day_type,
            "generated_at": datetime.now(UTC),
            "hours": [
                {
                    "transaction_hour": row[0],
                    "passenger_volume": row[1],
                    "transaction_count": row[2],
                    "observed_dates": row[3],
                }
                for row in rows
            ],
        }
    finally:
        con.close()


@router.get("/corridors", response_model=CorridorResponse)
def corridors(
    limit: int = Query(default=20, ge=1, le=100),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    con = _connection()
    try:
        clauses = ["route IS NOT NULL"]
        params: list[object] = []
        if date_from:
            clauses.append("service_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("service_date <= ?")
            params.append(date_to)
        params.append(limit)
        if date_from is None and date_to is None:
            has_catalog = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name='route_stop_catalog'"
            ).fetchone()[0]
            if has_catalog:
                rows = con.execute("""
                    WITH aggregate AS (
                        SELECT route, sum(passenger_volume)::BIGINT passenger_volume,
                               sum(transaction_count)::BIGINT transaction_count
                        FROM route_demand WHERE route IS NOT NULL GROUP BY route
                    ), labels AS (
                        SELECT route, count(*)::INTEGER stop_labels FROM route_stop_catalog GROUP BY route
                    )
                    SELECT a.route, a.passenger_volume, a.transaction_count,
                           coalesce(l.stop_labels, 0) stop_labels
                    FROM aggregate a LEFT JOIN labels l USING(route)
                    ORDER BY a.passenger_volume DESC LIMIT ?
                """, [limit]).fetchall()
            else:
                rows = con.execute(
                    f"""SELECT route, sum(passenger_volume)::BIGINT, sum(transaction_count)::BIGINT,
                               count(DISTINCT stop_id)::INTEGER
                        FROM stop_demand WHERE {' AND '.join(clauses)} GROUP BY route
                        ORDER BY sum(passenger_volume) DESC LIMIT ?""",
                    [limit],
                ).fetchall()
        else:
            rows = con.execute(
                f"""SELECT route, sum(passenger_volume)::BIGINT AS passenger_volume,
                           sum(transaction_count)::BIGINT AS transaction_count,
                           count(DISTINCT stop_id)::INTEGER AS stop_labels
                    FROM stop_demand WHERE {' AND '.join(clauses)}
                    GROUP BY route ORDER BY passenger_volume DESC LIMIT ?""",
                params,
            ).fetchall()
        return {
            "data_source": DATA_SOURCE,
            "generated_at": datetime.now(UTC),
            "routes": [
                {
                    "route": row[0],
                    "passenger_volume": row[1],
                    "transaction_count": row[2],
                    "stop_labels": row[3],
                }
                for row in rows
            ],
        }
    finally:
        con.close()


@router.get("/route-activity")
def route_activity(
    target_datetime: datetime,
    route_label: str = Query(min_length=1, max_length=100),
) -> dict:
    """Describe historical ETM ticket activity for an exact GTFS route label.

    This is intentionally not a crowd forecast: ETM timestamps are ticket
    transaction times, and route activity does not measure onboard occupancy.
    """
    con = _connection()
    try:
        match = con.execute(
            """SELECT route_short_name FROM gtfs_routes
               WHERE lower(trim(route_short_name))=lower(trim(?))
                  OR lower(trim(route_long_name))=lower(trim(?))
               LIMIT 1""",
            [route_label, route_label],
        ).fetchone()
        if not match:
            return {
                "status": "UNAVAILABLE", "route_label": route_label,
                "measure": "historical_ticket_activity", "data_source": DATA_SOURCE,
                "data_status": "historical", "comparable_days": 0,
                "passenger_ticket_volume_mean": None, "transaction_count_mean": None,
                "passenger_ticket_volume_range": None,
                "limitations": ["No exact route-label match exists between ETM and GTFS."],
            }
        canonical = match[0]
        target = target_datetime
        if target.tzinfo is not None:
            from zoneinfo import ZoneInfo
            target = target.astimezone(ZoneInfo("Asia/Kolkata"))
        target_date = target.date()
        # DuckDB dayofweek is Sunday=0, matching the ETM aggregates.
        weekday = (target_date.weekday() + 1) % 7
        rows = con.execute(
            """SELECT service_date, sum(passenger_volume)::DOUBLE,
                      sum(transaction_count)::DOUBLE
               FROM route_demand
               WHERE lower(trim(route))=lower(trim(?))
                 AND transaction_hour=? AND day_of_week=? AND service_date<?
               GROUP BY service_date ORDER BY service_date""",
            [canonical, target.hour, weekday, target_date],
        ).fetchall()
        volume = [float(row[1]) for row in rows]
        transactions = [float(row[2]) for row in rows]
        return {
            "status": "AVAILABLE" if rows else "UNAVAILABLE",
            "route_label": canonical,
            "target_weekday": target.strftime("%A"),
            "target_hour": target.hour,
            "measure": "historical_ticket_activity",
            "data_source": DATA_SOURCE,
            "data_status": "historical",
            "history_start_date": rows[0][0] if rows else None,
            "history_end_date": rows[-1][0] if rows else None,
            "comparable_days": len(rows),
            "passenger_ticket_volume_mean": round(sum(volume) / len(volume), 1) if volume else None,
            "transaction_count_mean": round(sum(transactions) / len(transactions), 1) if transactions else None,
            "passenger_ticket_volume_range": [int(min(volume)), int(max(volume))] if volume else None,
            "limitations": [
                "Historical October ticket activity for matching weekday and transaction hour; not a forecast.",
                "created_at is ticket transaction time, not verified boarding time.",
                "Ticket activity does not establish onboard load, physical crowding, or passenger capacity.",
                "Route matching uses exact GTFS route labels; no direction or individual bus trip is inferred.",
            ],
        }
    finally:
        con.close()


@router.get("/service-profile", response_model=ServiceProfileResponse)
def service_profile(date_from: date | None = None, date_to: date | None = None) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    con = _connection()
    try:
        available = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name='service_profile'"
        ).fetchone()[0]
        if not available:
            raise HTTPException(status_code=503, detail="Service profile aggregates are unavailable; reprocess ETM data")
        clauses: list[str] = []
        params: list[object] = []
        if date_from:
            clauses.append("service_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("service_date <= ?")
            params.append(date_to)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = con.execute(
            f"""SELECT is_ac, ticket_type_id, sum(passenger_volume)::BIGINT,
                       sum(transaction_count)::BIGINT, count(DISTINCT service_date)::INTEGER
                FROM service_profile{where} GROUP BY is_ac, ticket_type_id ORDER BY is_ac, ticket_type_id""",
            params,
        ).fetchall()
        return {
            "data_source": DATA_SOURCE,
            "generated_at": datetime.now(UTC),
            "semantic_caveat": (
                "is_ac and ticket_type_id are source fields; their business definitions and system coverage "
                "are unverified. These aggregates do not establish fleet share, fare meaning or occupancy."
            ),
            "groups": [
                {"is_ac": row[0], "ticket_type_id": row[1], "passenger_volume": row[2],
                 "transaction_count": row[3], "observed_dates": row[4]}
                for row in rows
            ],
        }
    finally:
        con.close()

