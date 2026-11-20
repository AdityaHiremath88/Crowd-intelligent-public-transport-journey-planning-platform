from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import duckdb

from backend_v2.config import DATABASE_PATH, GTFS_ZIP_PATH, REPORT_PATH

SCHEMA_VERSION = "1.0"
REQUIRED_FILES = {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
CALENDAR_FILES = {"calendar.txt", "calendar_dates.txt"}
OPTIONAL_FILES = {
    "calendar.txt", "calendar_dates.txt", "shapes.txt", "feed_info.txt",
    "transfers.txt", "frequencies.txt", "attributions.txt", "levels.txt",
    "pathways.txt", "translations.txt", "fare_attributes.txt", "fare_rules.txt",
    "fare_products.txt", "fare_leg_rules.txt", "fare_media.txt", "fare_transfer_rules.txt",
    "rider_categories.txt", "timeframes.txt", "locations.geojson", "booking_rules.txt",
}
REQUIRED_HEADERS = {
    "agency.txt": {"agency_name", "agency_url", "agency_timezone"},
    "stops.txt": {"stop_id", "stop_name", "stop_lat", "stop_lon"},
    "routes.txt": {"route_id", "route_type"},
    "trips.txt": {"route_id", "service_id", "trip_id"},
    "stop_times.txt": {"trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"},
    "calendar.txt": {"service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"},
    "calendar_dates.txt": {"service_id", "date", "exception_type"},
}
TIME_PATTERN = re.compile(r"^[0-9]+:[0-5][0-9]:[0-5][0-9]$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_string(value: Path | str) -> str:
    return str(value).replace("'", "''")


def _archive_members(archive: zipfile.ZipFile) -> dict[str, str]:
    by_basename: dict[str, str] = {}
    duplicates: set[str] = set()
    for name in archive.namelist():
        path = PurePosixPath(name)
        if name.endswith("/") or "__MACOSX" in path.parts or path.name.startswith("._"):
            continue
        basename = path.name.lower()
        if basename.endswith(".txt") and basename in OPTIONAL_FILES | REQUIRED_FILES:
            if basename in by_basename:
                duplicates.add(basename)
            by_basename[basename] = name
    if duplicates:
        raise ValueError(f"Duplicate GTFS archive members: {', '.join(sorted(duplicates))}")
    missing = REQUIRED_FILES - by_basename.keys()
    if missing:
        raise ValueError(f"GTFS archive is missing required files: {', '.join(sorted(missing))}")
    if not (CALENDAR_FILES & by_basename.keys()):
        raise ValueError("GTFS needs calendar.txt, calendar_dates.txt, or both")
    return by_basename


def _validate_headers(archive: zipfile.ZipFile, members: dict[str, str]) -> None:
    for basename, required in REQUIRED_HEADERS.items():
        if basename not in members:
            continue
        with archive.open(members[basename]) as raw:
            reader = csv.reader(__import__("io").TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            headers = set(next(reader, []))
        missing = required - headers
        if missing:
            raise ValueError(f"{basename} is missing columns: {', '.join(sorted(missing))}")
    with archive.open(members["routes.txt"]) as raw:
        headers = set(next(csv.reader(__import__("io").TextIOWrapper(raw, encoding="utf-8-sig", newline="")), []))
    if not ({"route_short_name", "route_long_name"} & headers):
        raise ValueError("routes.txt must contain route_short_name or route_long_name")


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0] or 0)


def import_gtfs(
    *, zip_path: Path = GTFS_ZIP_PATH, database_path: Path = DATABASE_PATH,
    report_path: Path = REPORT_PATH, overwrite: bool = False,
) -> dict:
    zip_path = zip_path.resolve()
    database_path = database_path.resolve()
    report_path = report_path.resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"GTFS ZIP not found: {zip_path}")
    if database_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to replace {database_path}; pass --overwrite to rebuild it.")
    with zipfile.ZipFile(zip_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"GTFS ZIP CRC check failed at {bad_member}")
        members = _archive_members(archive)
        _validate_headers(archive, members)

    selected_files = set(members)
    source_hash = _sha256(zip_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    issues: dict[str, int] = {}
    row_counts: dict[str, int] = {}
    table_names = {Path(name).stem for name in selected_files}

    with tempfile.TemporaryDirectory(prefix="yuktix_v2_gtfs_", dir=database_path.parent) as temp_dir:
        temp = Path(temp_dir)
        extracted = temp / "input"
        extracted.mkdir()
        with zipfile.ZipFile(zip_path) as archive:
            for basename, member in members.items():
                target = extracted / basename
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)

        stage_db = temp / "staged.duckdb"
        con = duckdb.connect(str(stage_db))
        try:
            con.execute("SET timezone='Asia/Kolkata'")
            for basename in sorted(selected_files):
                table = Path(basename).stem
                file_path = _sql_string(extracted / basename)
                con.execute(
                    f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto('{file_path}', header=true, all_varchar=true, sample_size=-1)"
                )
                row_counts[basename] = _count(con, f"SELECT count(*) FROM {table}")
                if basename in REQUIRED_FILES and row_counts[basename] == 0:
                    issues[f"empty_{table}"] = 1

            calendar_selects = []
            if "calendar" in table_names:
                calendar_selects.append("SELECT service_id FROM calendar")
            if "calendar_dates" in table_names:
                calendar_selects.append("SELECT service_id FROM calendar_dates")
            services_sql = " UNION " .join(calendar_selects)

            checks = {
                "duplicate_stop_ids": "SELECT count(*) FROM (SELECT stop_id FROM stops GROUP BY stop_id HAVING count(*)>1)",
                "duplicate_route_ids": "SELECT count(*) FROM (SELECT route_id FROM routes GROUP BY route_id HAVING count(*)>1)",
                "duplicate_trip_ids": "SELECT count(*) FROM (SELECT trip_id FROM trips GROUP BY trip_id HAVING count(*)>1)",
                "trips_missing_route": "SELECT count(*) FROM trips t LEFT JOIN routes r USING(route_id) WHERE r.route_id IS NULL",
                "stop_times_missing_trip": "SELECT count(*) FROM stop_times st LEFT JOIN trips t USING(trip_id) WHERE t.trip_id IS NULL",
                "stop_times_missing_stop": "SELECT count(*) FROM stop_times st LEFT JOIN stops s USING(stop_id) WHERE s.stop_id IS NULL",
                "trips_without_stop_times": "SELECT count(*) FROM trips t LEFT JOIN (SELECT DISTINCT trip_id FROM stop_times) s USING(trip_id) WHERE s.trip_id IS NULL",
                "duplicate_trip_stop_sequences": "SELECT count(*) FROM (SELECT trip_id, stop_sequence FROM stop_times GROUP BY trip_id,stop_sequence HAVING count(*)>1)",
                "invalid_stop_sequences": "SELECT count(*) FROM stop_times WHERE try_cast(stop_sequence AS INTEGER) IS NULL OR try_cast(stop_sequence AS INTEGER)<0",
                "invalid_stop_coordinates": "SELECT count(*) FROM stops WHERE try_cast(stop_lat AS DOUBLE) NOT BETWEEN -90 AND 90 OR try_cast(stop_lon AS DOUBLE) NOT BETWEEN -180 AND 180 OR try_cast(stop_lat AS DOUBLE) IS NULL OR try_cast(stop_lon AS DOUBLE) IS NULL",
                "invalid_stop_times": "SELECT count(*) FROM stop_times WHERE NOT regexp_full_match(arrival_time,'[0-9]+:[0-5][0-9]:[0-5][0-9]') OR NOT regexp_full_match(departure_time,'[0-9]+:[0-5][0-9]:[0-5][0-9]')",
                "trips_missing_service_calendar": f"SELECT count(*) FROM trips t LEFT JOIN ({services_sql}) c USING(service_id) WHERE c.service_id IS NULL",
            }
            for name, sql in checks.items():
                issues[name] = _count(con, sql)
            issues["trips_without_block_id"] = (
                _count(con, "SELECT count(*) FROM trips WHERE block_id IS NULL OR trim(block_id)='' ")
                if "block_id" in {row[0] for row in con.execute("DESCRIBE trips").fetchall()} else row_counts["trips.txt"]
            )

            time_expr = lambda col: (
                f"(try_cast(split_part({col},':',1) AS BIGINT)*3600 + "
                f"try_cast(split_part({col},':',2) AS BIGINT)*60 + "
                f"try_cast(split_part({col},':',3) AS BIGINT))"
            )
            issues["decreasing_trip_times"] = _count(
                con,
                f"""SELECT count(*) FROM (
                       SELECT trip_id, try_cast(stop_sequence AS INTEGER) stop_sequence,
                              lag({time_expr('departure_time')}) OVER (
                                  PARTITION BY trip_id ORDER BY try_cast(stop_sequence AS INTEGER)
                              ) previous_departure,
                              {time_expr('arrival_time')} arrival_seconds
                       FROM stop_times
                   ) q WHERE previous_departure>arrival_seconds""",
            )

            fatal_schedule_checks = {
                "duplicate_stop_ids", "duplicate_route_ids", "duplicate_trip_ids",
                "trips_missing_route", "stop_times_missing_trip", "stop_times_missing_stop",
                "trips_without_stop_times", "duplicate_trip_stop_sequences", "invalid_stop_sequences",
                "invalid_stop_times", "trips_missing_service_calendar", "decreasing_trip_times",
            }
            usable = not any(issues.get(key, 0) for key in fatal_schedule_checks)
            date_parts = []
            if "calendar" in table_names:
                date_parts.append(
                    "SELECT try_strptime(start_date,'%Y%m%d') d FROM calendar UNION ALL "
                    "SELECT try_strptime(end_date,'%Y%m%d') d FROM calendar"
                )
            if "calendar_dates" in table_names:
                date_parts.append("SELECT try_strptime(date,'%Y%m%d') d FROM calendar_dates")
            date_rows = con.execute(
                "SELECT min(d),max(d) FROM (" + " UNION ALL ".join(date_parts) + ")"
            ).fetchone()
            service_start = date_rows[0].date() if date_rows[0] else None
            service_end = date_rows[1].date() if date_rows[1] else None

            imported_at = datetime.now(UTC)
            metadata = {
                "imported_at": imported_at,
                "source_file": zip_path.name,
                "source_sha256": source_hash,
                "source_size_bytes": zip_path.stat().st_size,
                "schema_version": SCHEMA_VERSION,
                "usable_for_scheduled_routing": usable,
                "service_start_date": service_start,
                "service_end_date": service_end,
                "row_counts_json": json.dumps(row_counts, sort_keys=True),
                "issues_json": json.dumps(issues, sort_keys=True),
                "files_json": json.dumps(sorted(selected_files)),
            }
            con.execute("""CREATE TABLE gtfs_import_metadata (
                imported_at TIMESTAMPTZ, source_file VARCHAR, source_sha256 VARCHAR,
                source_size_bytes BIGINT, schema_version VARCHAR,
                usable_for_scheduled_routing BOOLEAN, service_start_date DATE,
                service_end_date DATE, row_counts_json VARCHAR, issues_json VARCHAR,
                files_json VARCHAR
            )""")
            con.execute(
                "INSERT INTO gtfs_import_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                list(metadata.values()),
            )
            con.execute("CHECKPOINT")
        finally:
            con.close()

        os.replace(stage_db, database_path)

    finished_at = datetime.now(UTC)
    report = {
        "status": "ready" if usable else "loaded_unusable_for_scheduled_routing",
        "source_file": zip_path.name,
        "source_sha256": source_hash,
        "source_size_bytes": zip_path.stat().st_size,
        "imported_at": imported_at.isoformat(),
        "completed_at": finished_at.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "files_loaded": sorted(selected_files),
        "row_counts": row_counts,
        "issues": issues,
        "usable_for_scheduled_routing": usable,
        "service_start_date": service_start.isoformat() if service_start else None,
        "service_end_date": service_end.isoformat() if service_end else None,
        "trips_with_block_id": row_counts["trips.txt"] - issues["trips_without_block_id"],
        "database_path": str(database_path),
        "limitations": [
            "GTFS schedule trips do not identify ETM ticket rows or actual vehicle numbers.",
            "A blank GTFS block_id cannot be used to infer vehicle blocks.",
            "Static GTFS times are schedules, not live arrivals; publisher stop times may be approximate.",
            "GTFS stop coordinates are publisher-listed and are not independently field-verified.",
        ],
    }
    temporary_report = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary_report, report_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import and validate static GTFS into the Yuktix v2 DuckDB.")
    parser.add_argument("--zip", type=Path, default=GTFS_ZIP_PATH)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(json.dumps(import_gtfs(zip_path=args.zip, database_path=args.database, report_path=args.report, overwrite=args.overwrite), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
