from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from backend_v2.config import DATABASE_PATH
from backend_v2.routing import ScheduledTrip, StopEvent, build_search_index, parse_gtfs_time, SearchIndex


@dataclass(frozen=True)
class ScheduleData:
    trips: tuple[ScheduledTrip, ...]
    search_index: SearchIndex
    calendar_rows: tuple[dict[str, str], ...]
    exception_rows: tuple[dict[str, str], ...]
    route_labels: dict[str, str]
    route_short_names: dict[str, str]
    stop_names: dict[str, str]
    stop_coordinates: dict[str, tuple[float, float]]
    timezone: str
    service_start_date: date | None
    service_end_date: date | None


@lru_cache(maxsize=2)
def _load_cached(path_string: str, mtime_ns: int, size: int) -> ScheduleData:
    del mtime_ns, size  # cache key changes when the imported database changes.
    con = duckdb.connect(path_string, read_only=True)
    try:
        metadata = con.execute(
            """SELECT usable_for_scheduled_routing, service_start_date, service_end_date
               FROM gtfs_import_metadata ORDER BY imported_at DESC LIMIT 1"""
        ).fetchone()
        if not metadata or not metadata[0]:
            raise RuntimeError("The imported GTFS feed is not usable for scheduled routing.")
        service_start, service_end = metadata[1], metadata[2]
        if hasattr(service_start, "date"):
            service_start = service_start.date()
        if hasattr(service_end, "date"):
            service_end = service_end.date()

        calendar_rows = tuple(
            dict(zip((d[0] for d in con.execute("DESCRIBE calendar").fetchall()), row, strict=True))
            for row in con.execute("SELECT * FROM calendar").fetchall()
        ) if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='calendar'").fetchone()[0] else ()
        exception_rows = tuple(
            dict(zip((d[0] for d in con.execute("DESCRIBE calendar_dates").fetchall()), row, strict=True))
            for row in con.execute("SELECT * FROM calendar_dates").fetchall()
        ) if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='calendar_dates'").fetchone()[0] else ()

        route_columns = {row[0] for row in con.execute("DESCRIBE routes").fetchall()}
        route_rows = con.execute("SELECT * FROM routes").fetchall()
        route_names = [row[0] for row in con.execute("DESCRIBE routes").fetchall()]
        routes = [dict(zip(route_names, row, strict=True)) for row in route_rows]
        short_names = {row["route_id"]: row.get("route_short_name") or "" for row in routes}
        route_labels = {
            row["route_id"]: row.get("route_short_name") or row.get("route_long_name") or row["route_id"]
            for row in routes
        }

        stop_rows = con.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops").fetchall()
        stop_names = {row[0]: row[1] or row[0] for row in stop_rows}
        stop_coordinates = {}
        for stop_id, _, lat, lon in stop_rows:
            try:
                stop_coordinates[stop_id] = (float(lat), float(lon))
            except (ValueError, TypeError):
                pass

        trip_rows = con.execute("SELECT trip_id, route_id, service_id FROM trips").fetchall()
        groups: dict[str, list[tuple]] = {}
        for row in con.execute(
            """SELECT trip_id, stop_id, stop_sequence, arrival_time, departure_time
               FROM stop_times ORDER BY trip_id, try_cast(stop_sequence AS INTEGER)"""
        ).fetchall():
            groups.setdefault(row[0], []).append(row)
        trips = []
        for trip_id, route_id, service_id in trip_rows:
            events = tuple(
                StopEvent(stop_id=stop_id, stop_name=stop_names.get(stop_id, stop_id),
                          stop_sequence=int(sequence), arrival_seconds=parse_gtfs_time(arrival),
                          departure_seconds=parse_gtfs_time(departure))
                for _, stop_id, sequence, arrival, departure in groups.get(trip_id, [])
            )
            if len(events) < 2:
                continue
            trips.append(ScheduledTrip(trip_id, route_id, service_id, events))
        agency_rows = con.execute("SELECT agency_timezone FROM agency LIMIT 1").fetchall()
        timezone = agency_rows[0][0] if agency_rows and agency_rows[0][0] else "Asia/Kolkata"
        ZoneInfo(timezone)
        trip_tuple = tuple(trips)
        return ScheduleData(
            trips=trip_tuple,
            search_index=build_search_index(trip_tuple),
            calendar_rows=calendar_rows,
            exception_rows=exception_rows,
            route_labels=route_labels,
            route_short_names=short_names,
            stop_names=stop_names,
            stop_coordinates=stop_coordinates,
            timezone=timezone,
            service_start_date=service_start,
            service_end_date=service_end,
        )
    finally:
        con.close()


def load_schedule_data(database_path: Path = DATABASE_PATH) -> ScheduleData:
    path = database_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Yuktix v2 GTFS database not found: {path}")
    stat = path.stat()
    return _load_cached(str(path), stat.st_mtime_ns, stat.st_size)
