from __future__ import annotations

import argparse
import json
import tempfile
import tracemalloc
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from time import perf_counter
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, ZipFile

import duckdb
import numpy as np

from app.config import DATABASE_PATH, PROJECT_ROOT
from app.api.routes import analytics, routes, stops
from app.api.routes import community, vehicles
from app.routing.journey_search import (
    ScheduledTrip,
    StopEvent,
    build_journey_search_index,
    search_journeys,
)
from scripts.process_gtfs import process_gtfs


def _percentile(values: list[float], quantile: float) -> float:
    return float(np.percentile(np.asarray(values), quantile))


def _measure(name: str, function, repetitions: int) -> dict:
    samples = []
    result = None
    for _ in range(repetitions):
        started = perf_counter()
        result = function()
        samples.append((perf_counter() - started) * 1000)
    tracemalloc.start()
    function()
    _, python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "name": name,
        "repetitions": repetitions,
        "median_ms": round(median(samples), 3),
        "p95_ms": round(_percentile(samples, 95), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
        "single_call_python_tracemalloc_peak_bytes": python_peak,
    }


def _clock(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _make_synthetic_trips(route_count: int = 543, departures_per_route: int = 31, stops_per_route: int = 24) -> tuple[list[ScheduledTrip], str, str]:
    trips = []
    transfer_hub = "SYNTHETIC_HUB"
    origin = "SYNTHETIC_ORIGIN"
    destination = "SYNTHETIC_DESTINATION"
    for route_index in range(route_count):
        for departure_index in range(departures_per_route):
            trip_id = f"synthetic_r{route_index}_t{departure_index}"
            route_offset = 52 * 60 if route_index == 1 else route_index * 60
            start = 4 * 3600 + departure_index * 8 * 60 + route_offset
            events = []
            for sequence in range(stops_per_route):
                if route_index == 0:
                    stop_id = origin if sequence == 0 else transfer_hub if sequence == stops_per_route - 1 else f"R0_S{sequence}"
                elif route_index == 1:
                    stop_id = transfer_hub if sequence == 0 else destination if sequence == stops_per_route - 1 else f"R1_S{sequence}"
                else:
                    stop_id = transfer_hub if sequence == 0 else f"R{route_index}_S{sequence}"
                seconds = start + sequence * 120
                events.append(StopEvent(stop_id, stop_id, sequence + 1, seconds, seconds))
            trips.append(ScheduledTrip(trip_id, f"synthetic_route_{route_index}", "daily", tuple(events)))
    return trips, origin, destination


def _benchmark_journey_search(repetitions: int) -> dict:
    trips, origin, destination = _make_synthetic_trips()
    started = perf_counter()
    tracemalloc.start()
    index = build_journey_search_index(trips)
    _, index_python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    index_build_ms = (perf_counter() - started) * 1000
    journey_repetitions = min(repetitions, 5)
    result = _measure(
        "synthetic_gtfs_bounded_journey_search_16833_trips_403992_stop_events",
        lambda: search_journeys(
            trips, origin, destination, 8 * 3600, {"daily"}, max_transfers=1,
            limit=10, search_index=index,
        ),
        journey_repetitions,
    )
    journeys = search_journeys(
        trips, origin, destination, 8 * 3600, {"daily"}, max_transfers=1, search_index=index
    )
    result["synthetic_trips"] = len(trips)
    result["synthetic_stop_events"] = sum(len(trip.events) for trip in trips)
    result["journeys_returned"] = len(journeys)
    result["minimum_transfers_returned"] = min((item.transfers for item in journeys), default=None)
    result["search_index_build_ms_one_time"] = round(index_build_ms, 3)
    result["search_index_build_python_peak_bytes"] = index_python_peak
    result["data_status"] = "synthetic_performance_fixture_only"
    return result


def _write_synthetic_gtfs(path: Path, trip_count: int = 20_000, stops_per_trip: int = 20) -> dict:
    route_count = 100
    stop_count = route_count * stops_per_trip
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr(
            "agency.txt",
            "agency_name,agency_url,agency_timezone\nSynthetic Benchmark,https://example.invalid,Asia/Kolkata\n",
        )
        with archive.open("stops.txt", "w") as binary:
            import io
            handle = io.TextIOWrapper(binary, encoding="utf-8", newline="", write_through=True)
            handle.write("stop_id,stop_name,stop_lat,stop_lon\n")
            for index in range(stop_count):
                handle.write(f"s{index},Synthetic stop {index},28.5,77.2\n")
            handle.flush()
            handle.detach()
        with archive.open("routes.txt", "w") as binary:
            import io
            handle = io.TextIOWrapper(binary, encoding="utf-8", newline="", write_through=True)
            handle.write("route_id,route_short_name,route_type\n")
            for index in range(route_count):
                handle.write(f"r{index},Synthetic {index},3\n")
            handle.flush()
            handle.detach()
        with archive.open("trips.txt", "w") as binary:
            import io
            handle = io.TextIOWrapper(binary, encoding="utf-8", newline="", write_through=True)
            handle.write("route_id,service_id,trip_id\n")
            for index in range(trip_count):
                handle.write(f"r{index % route_count},daily,t{index}\n")
            handle.flush()
            handle.detach()
        with archive.open("stop_times.txt", "w") as binary:
            import io
            handle = io.TextIOWrapper(binary, encoding="utf-8", newline="", write_through=True)
            handle.write("trip_id,arrival_time,departure_time,stop_id,stop_sequence\n")
            for index in range(trip_count):
                route_index = index % route_count
                start = 4 * 3600 + (index // route_count) * 240
                for sequence in range(stops_per_trip):
                    clock = _clock(start + sequence * 60)
                    stop_id = route_index * stops_per_trip + sequence
                    handle.write(f"t{index},{clock},{clock},s{stop_id},{sequence + 1}\n")
            handle.flush()
            handle.detach()
        archive.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "daily,1,1,1,1,1,1,1,20260101,20271231\n",
        )
    return {"trips": trip_count, "stops": stop_count, "stop_times": trip_count * stops_per_trip}


def _benchmark_gtfs_import() -> dict:
    with tempfile.TemporaryDirectory(prefix="crowdwise_gtfs_benchmark_") as temporary:
        directory = Path(temporary)
        feed_path = directory / "synthetic_benchmark_feed.zip"
        database_path = directory / "synthetic_benchmark.duckdb"
        feed_counts = _write_synthetic_gtfs(feed_path)
        started = perf_counter()
        report = process_gtfs(feed_path, database_path, directory / "quality.json")
        elapsed = (perf_counter() - started) * 1000
        return {
            "name": "synthetic_gtfs_import_20000_trips_400000_stop_times",
            "data_status": "synthetic_performance_fixture_only",
            "input_rows_by_table": feed_counts,
            "zip_bytes": feed_path.stat().st_size,
            "database_bytes": database_path.stat().st_size,
            "elapsed_ms": round(elapsed, 3),
            "quality_usable_for_routing": report["usable_for_scheduled_routing"],
            "quality_issue_count": sum(report["issues"].values()),
        }


def benchmark(database_path: Path = DATABASE_PATH, repetitions: int = 21) -> dict:
    if not database_path.is_file():
        raise FileNotFoundError(f"Processed ETM database not found: {database_path}")
    con = duckdb.connect(str(database_path), read_only=True)
    try:
        busiest_stop = con.execute(
            "SELECT stop_id FROM stop_demand GROUP BY stop_id ORDER BY sum(passenger_volume) DESC LIMIT 1"
        ).fetchone()[0]
        busiest_route = con.execute(
            "SELECT route FROM route_demand GROUP BY route ORDER BY sum(passenger_volume) DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()

    endpoint_cases = [
        _measure("stop_search_100", lambda: stops.list_stops(q="Saket", limit=100, offset=0, source="etm"), repetitions),
        _measure("stop_demand_page_200", lambda: stops.stop_demand(
            busiest_stop, route=None, day_of_week=None, transaction_hour=None,
            date_from=None, date_to=None, limit=200, offset=0
        ), repetitions),
        _measure("route_catalog_50", lambda: routes.list_routes(q=None, limit=50, offset=0), repetitions),
        _measure("route_profile_hour_and_weekday", lambda: routes.route_profile(
            route_label=busiest_route, date_from=None, date_to=None
        ), repetitions),
        _measure("peak_hours_all_days", lambda: analytics.peak_hours(day_type="all"), repetitions),
        _measure("trends_daily_31_days", lambda: analytics.trends(granularity="day", date_from=None, date_to=None), repetitions),
        _measure("trends_weekly_5_points", lambda: analytics.trends(granularity="week", date_from=None, date_to=None), repetitions),
        _measure("corridors_top_20", lambda: analytics.corridors(limit=20, date_from=None, date_to=None), repetitions),
        _measure("service_profile", lambda: analytics.service_profile(date_from=None, date_to=None), repetitions),
        _measure("overview", analytics.overview, repetitions),
    ]
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    auxiliary_cases = [
        _measure("community_reports_list", lambda: community.recent_crowd_reports(busiest_stop), repetitions),
        _measure("community_crowd_aggregate", lambda: community.stop_crowding(busiest_stop), repetitions),
        _measure("opt_in_presence_aggregate", lambda: community.stop_presence(busiest_stop), repetitions),
        _measure("realtime_feed_health", vehicles.realtime_status, repetitions),
        _measure("ticket_activity_forecast_staleness_gate", lambda: community.predict_ticket_activity(
            stop_id=busiest_stop, target_date=today + timedelta(days=1), hour=8
        ), repetitions),
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": __import__("sys").version.split()[0],
            "duckdb": duckdb.__version__,
            "database_bytes": database_path.stat().st_size,
            "database_path": str(database_path),
            "warm_cache": True,
            "measurement": "direct synchronous handlers; excludes HTTP and JSON serialization",
        },
        "repetitions": repetitions,
        "actual_etm_queries": endpoint_cases,
        "backend_auxiliary_queries": auxiliary_cases,
        "synthetic_journey_search": _benchmark_journey_search(repetitions),
        "synthetic_gtfs_import": _benchmark_gtfs_import(),
        "memory_note": "Python tracemalloc is reported per handler call; DuckDB native allocations and OS page cache are excluded.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark actual ETM APIs and isolated synthetic routing/GTFS workloads.")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--repetitions", type=int, default=21)
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "outputs" / "backend_benchmark.json")
    args = parser.parse_args()
    if args.repetitions < 3:
        parser.error("--repetitions must be at least 3")
    result = benchmark(args.database.resolve(), args.repetitions)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()


