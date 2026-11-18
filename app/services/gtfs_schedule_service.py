from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.config import DATABASE_PATH
from app.database import connect
from app.data_pipeline.gtfs_loader import parse_gtfs_time
from app.routing.journey_search import JourneySearchIndex, ScheduledTrip, StopEvent, build_journey_search_index

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GtfsScheduleData:
    trips: tuple[ScheduledTrip, ...]
    calendar_rows: tuple[dict[str, str], ...]
    exception_rows: tuple[dict[str, str], ...]
    route_labels: dict[str, str]
    stop_names: dict[str, str]
    stop_coordinates: dict[str, tuple[float, float]]
    timezone: str
    service_start_date: date | None
    service_end_date: date | None
    search_index: JourneySearchIndex


_cache_key: tuple[str, int, int] | None = None
_cache_value: GtfsScheduleData | None = None


def _table_rows(con, table_name: str) -> list[dict[str, str]]:
    return [dict(zip((column[0] for column in con.description), row, strict=True)) for row in con.execute(f'SELECT * FROM "{table_name}"').fetchall()]


def load_schedule_data(database_path: Path | None = None) -> GtfsScheduleData | None:
    """Load validated GTFS tables from DuckDB; cache by database file version."""
    global _cache_key, _cache_value
    database_path = database_path or DATABASE_PATH
    if not database_path.exists():
        return None
    stat = database_path.stat()
    key = (str(database_path.resolve()), stat.st_mtime_ns, stat.st_size)
    if key == _cache_key:
        return _cache_value

    con = connect(read_only=True, path=database_path)
    try:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        required = {"gtfs_stops", "gtfs_routes", "gtfs_trips", "gtfs_stop_times"}
        if not required.issubset(existing):
            _cache_key, _cache_value = key, None
            return None

        # Do not serve a schedule unless ingestion's integrity checks passed.
        # This also prevents stale or manually-created partial GTFS tables from
        # looking like a valid feed just because the four core tables exist.
        if "gtfs_quality" not in existing:
            _cache_key, _cache_value = key, None
            return None
        quality = con.execute(
            "SELECT usable_for_scheduled_routing FROM gtfs_quality LIMIT 1"
        ).fetchone()
        if not quality or str(quality[0]).lower() not in {"true", "1"}:
            _cache_key, _cache_value = key, None
            return None
        service_window = con.execute(
            "SELECT service_start_date, service_end_date FROM gtfs_quality LIMIT 1"
        ).fetchone()
        def as_date(value) -> date | None:
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            if value:
                try:
                    return date.fromisoformat(str(value))
                except ValueError:
                    return None
            return None
        service_start = as_date(service_window[0]) if service_window else None
        service_end = as_date(service_window[1]) if service_window else None

        calendar_rows = tuple(_table_rows(con, "gtfs_calendar")) if "gtfs_calendar" in existing else ()
        exception_rows = tuple(_table_rows(con, "gtfs_calendar_dates")) if "gtfs_calendar_dates" in existing else ()
        routes = _table_rows(con, "gtfs_routes")
        route_labels = {
            row["route_id"]: row.get("route_short_name") or row.get("route_long_name") or row["route_id"]
            for row in routes
        }
        stops = _table_rows(con, "gtfs_stops")
        stop_names = {stop["stop_id"]: stop.get("stop_name") or stop["stop_id"] for stop in stops}
        stop_coordinates: dict[str, tuple[float, float]] = {}
        for stop in stops:
            try:
                stop_coordinates[stop["stop_id"]] = (float(stop["stop_lat"]), float(stop["stop_lon"]))
            except (KeyError, TypeError, ValueError):
                continue

        rows = con.execute(
            """
            SELECT st.trip_id, t.route_id, t.service_id, st.stop_id,
                   coalesce(nullif(s.stop_name, ''), st.stop_id) AS stop_name,
                   st.stop_sequence, st.arrival_time, st.departure_time
            FROM gtfs_stop_times st
            JOIN gtfs_trips t USING (trip_id)
            LEFT JOIN gtfs_stops s USING (stop_id)
            ORDER BY st.trip_id, try_cast(st.stop_sequence AS INTEGER)
            """
        ).fetchall()
        grouped: dict[str, list[tuple]] = {}
        for row in rows:
            grouped.setdefault(row[0], []).append(row)

        trips: list[ScheduledTrip] = []
        skipped = 0
        for trip_id, trip_rows in grouped.items():
            first = trip_rows[0]
            try:
                events = tuple(
                    StopEvent(
                        stop_id=row[3],
                        stop_name=row[4],
                        stop_sequence=int(row[5]),
                        arrival_seconds=parse_gtfs_time(row[6]),
                        departure_seconds=parse_gtfs_time(row[7]),
                    )
                    for row in trip_rows
                )
                if len(events) < 2:
                    skipped += 1
                    continue
                if any(left.stop_sequence >= right.stop_sequence for left, right in zip(events, events[1:])):
                    skipped += 1
                    continue
                if any(event.arrival_seconds > event.departure_seconds for event in events):
                    skipped += 1
                    continue
                if any(left.departure_seconds > right.arrival_seconds for left, right in zip(events, events[1:])):
                    skipped += 1
                    continue
                trips.append(ScheduledTrip(trip_id, first[1], first[2], events))
            except (TypeError, ValueError):
                skipped += 1
        if skipped:
            logger.warning("GTFS schedules omitted invalid trips count=%d", skipped)
        agency_rows = _table_rows(con, "gtfs_agency") if "gtfs_agency" in existing else []
        timezone = agency_rows[0].get("agency_timezone", "Asia/Kolkata") if agency_rows else "Asia/Kolkata"
        value = GtfsScheduleData(
            tuple(trips), calendar_rows, exception_rows, route_labels, stop_names, stop_coordinates,
            timezone, service_start, service_end, build_journey_search_index(trips)
        )
        _cache_key, _cache_value = key, value
        return value
    finally:
        con.close()


def clear_schedule_cache() -> None:
    global _cache_key, _cache_value
    _cache_key, _cache_value = None, None



