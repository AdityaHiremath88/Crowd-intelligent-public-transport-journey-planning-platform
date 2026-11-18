from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.database import connect
from app.schemas import TicketActivityForecastResponse

MAX_HORIZON_DAYS = 14
MAX_SOURCE_AGE_DAYS = 14
MIN_COMPARABLE_DAYS = 3


def forecast_ticket_activity(
    *, stop_id: str, target_date: date, target_hour: int, today: date | None = None,
) -> TicketActivityForecastResponse:
    now = datetime.now(UTC)
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if not 0 <= target_hour <= 23:
        raise HTTPException(status_code=422, detail="hour must be between 0 and 23")
    if target_date <= today or target_date > today + timedelta(days=MAX_HORIZON_DAYS):
        raise HTTPException(status_code=422, detail=f"target_date must be within the next {MAX_HORIZON_DAYS} days")
    try:
        con = connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Processed ETM data is unavailable") from exc
    try:
        name = con.execute("SELECT stop_name FROM stop_catalog WHERE stop_id=?", [stop_id]).fetchone()
        if not name:
            raise HTTPException(status_code=404, detail=f"Unknown ETM stop identifier: {stop_id}")
        max_value = con.execute(
            "SELECT max(dataset_max_timestamp) FROM data_quality WHERE dataset_name='etm'"
        ).fetchone()[0]
        if max_value is None:
            raise HTTPException(status_code=503, detail="ETM dataset coverage metadata is unavailable")
        historical_max = max_value.date() if isinstance(max_value, datetime) else max_value
        common = dict(
            stop_id=stop_id, target_date=target_date, target_hour=target_hour,
            comparable_days=0, historical_max_date=historical_max,
            method="mean passenger ticket volume and transaction count across observed prior dates with matching stop, weekday and transaction hour",
            data_source="October-Delhi ETM CSV", generated_at=now,
            limitations=[
                "Forecast target is ticket transaction activity represented by the ETM extract, not a physical queue or verified boarding count.",
                "created_at is transaction time; ticket destination and vehicle trip are not validated.",
                "The single October month does not capture annual seasonality, holidays or changing operations.",
                "The historical min/max is a sample range, not a prediction interval.",
            ],
        )
        if (today - historical_max).days > MAX_SOURCE_AGE_DAYS:
            return TicketActivityForecastResponse(
                **common, status="STALE", predicted_passenger_ticket_volume=None,
                predicted_transaction_count=None, historical_range_passenger_volume=None,
                evidence_quality="source_too_old_for_forecast",
            )
        if historical_max >= target_date:
            raise HTTPException(status_code=422, detail="Target date must follow the latest observed ETM date")
        dow = (target_date.weekday() + 1) % 7  # DuckDB/ETM uses Sunday=0.
        rows = con.execute(
            """SELECT service_date, sum(passenger_volume)::DOUBLE, sum(transaction_count)::DOUBLE
               FROM stop_demand
               WHERE stop_id=? AND day_of_week=? AND transaction_hour=? AND service_date<?
               GROUP BY service_date ORDER BY service_date""",
            [stop_id, dow, target_hour, target_date],
        ).fetchall()
        rows = [row for row in rows if (target_date - row[0]).days <= 35]
        common["comparable_days"] = len(rows)
        if len(rows) < MIN_COMPARABLE_DAYS:
            return TicketActivityForecastResponse(
                **common, status="UNAVAILABLE", predicted_passenger_ticket_volume=None,
                predicted_transaction_count=None,
                historical_range_passenger_volume=(min(int(row[1]) for row in rows), max(int(row[1]) for row in rows)) if rows else None,
                evidence_quality="insufficient_comparable_days",
            )
        volumes = [float(row[1]) for row in rows]
        transactions = [float(row[2]) for row in rows]
        return TicketActivityForecastResponse(
            **common,
            status="PREDICTED",
            predicted_passenger_ticket_volume=round(sum(volumes) / len(volumes), 3),
            predicted_transaction_count=round(sum(transactions) / len(transactions), 3),
            historical_range_passenger_volume=(int(min(volumes)), int(max(volumes))),
            evidence_quality="baseline_only_not_calibrated",
        )
    finally:
        con.close()
