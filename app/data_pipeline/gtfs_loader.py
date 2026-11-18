from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

REQUIRED_FILES = {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
CALENDAR_FILES = {"calendar.txt", "calendar_dates.txt"}
OPTIONAL_FILES = {"shapes.txt", "transfers.txt", "frequencies.txt", "feed_info.txt"}
REQUIRED_COLUMNS = {
    "agency.txt": {"agency_name", "agency_url", "agency_timezone"},
    "stops.txt": {"stop_id", "stop_name", "stop_lat", "stop_lon"},
    "routes.txt": {"route_id", "route_type"},
    "trips.txt": {"route_id", "service_id", "trip_id"},
    "stop_times.txt": {"trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"},
    "calendar.txt": {"service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"},
    "calendar_dates.txt": {"service_id", "date", "exception_type"},
    "shapes.txt": {"shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"},
    "transfers.txt": {"from_stop_id", "to_stop_id", "transfer_type"},
    "frequencies.txt": {"trip_id", "start_time", "end_time", "headway_secs"},
    "feed_info.txt": {"feed_publisher_name", "feed_publisher_url", "feed_lang"},
}


def parse_gtfs_time(value: str) -> int:
    """Convert GTFS HH:MM:SS, including hours >= 24, to seconds from service-day start."""
    pieces = value.strip().split(":")
    if len(pieces) != 3:
        raise ValueError(f"Invalid GTFS time {value!r}; expected HH:MM:SS")
    try:
        hours, minutes, seconds = (int(piece) for piece in pieces)
    except ValueError as exc:
        raise ValueError(f"Invalid GTFS time {value!r}; expected numeric components") from exc
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"Invalid GTFS time {value!r}; minutes and seconds must be 0..59")
    return hours * 3600 + minutes * 60 + seconds


@dataclass
class GtfsAudit:
    source: str
    files: list[str]
    optional_files: list[str]
    duplicate_archive_basenames: list[str]
    missing_required_files: list[str]
    calendar_available: bool
    row_counts: dict[str, int]
    missing_columns: dict[str, list[str]]
    parse_errors: list[str]
    usable_for_scheduled_routing: bool


def inspect_gtfs(path: Path) -> GtfsAudit:
    if not path.is_file():
        raise FileNotFoundError(f"GTFS ZIP not found: {path}")
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        name_groups: dict[str, list[str]] = {}
        for name in names:
            name_groups.setdefault(Path(name).name.lower(), []).append(name)
        duplicate_basenames = sorted(name for name, group in name_groups.items() if len(group) > 1)
        basename_map = {name: group[0] for name, group in name_groups.items()}
        files = sorted(basename_map)
        optional = sorted(OPTIONAL_FILES & set(basename_map))
        missing = sorted(REQUIRED_FILES - set(basename_map))
        calendar_ok = bool(CALENDAR_FILES & set(basename_map))
        row_counts: dict[str, int] = {}
        missing_columns: dict[str, list[str]] = {}
        errors: list[str] = []
        check_files = (REQUIRED_FILES | (CALENDAR_FILES & set(basename_map)) | OPTIONAL_FILES) & set(basename_map)
        if duplicate_basenames:
            errors.append(f"Duplicate archive basenames are ambiguous: {', '.join(duplicate_basenames)}")
        for basename in sorted(check_files):
            member = basename_map[basename]
            try:
                with archive.open(member) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text)
                    headers = set(reader.fieldnames or [])
                    expected = REQUIRED_COLUMNS.get(basename, set())
                    absent = sorted(expected - headers)
                    if basename == "routes.txt" and not ({"route_short_name", "route_long_name"} & headers):
                        absent.append("route_short_name or route_long_name")
                    if absent:
                        missing_columns[basename] = absent
                    count = sum(1 for _ in reader)
                    row_counts[basename] = count
                    if basename in REQUIRED_FILES and count == 0:
                        errors.append(f"{basename} has no data rows")
                    if basename == "stop_times.txt":
                        # A second streaming pass is unnecessary: rows are parsed
                        # here to catch malformed GTFS clock values before loading.
                        raw.seek(0)
                        text.seek(0)
                        timed_reader = csv.DictReader(text)
                        invalid_times = 0
                        for row in timed_reader:
                            for field in ("arrival_time", "departure_time"):
                                try:
                                    parse_gtfs_time(row.get(field, ""))
                                except (TypeError, ValueError):
                                    invalid_times += 1
                        if invalid_times:
                            errors.append(f"stop_times.txt has {invalid_times} invalid arrival/departure time fields")
            except (UnicodeDecodeError, csv.Error, OSError) as exc:
                errors.append(f"{basename}: {exc}")
        if not calendar_ok:
            errors.append("No calendar.txt or calendar_dates.txt found")
        calendar_rows = sum(row_counts.get(name, 0) for name in CALENDAR_FILES)
        if calendar_ok and calendar_rows == 0:
            errors.append("Calendar files contain no service rows")
        required_ok = not missing and calendar_ok and not missing_columns and not errors
        return GtfsAudit(
            source=path.name,
            files=files,
            optional_files=optional,
            duplicate_archive_basenames=duplicate_basenames,
            missing_required_files=missing,
            calendar_available=calendar_ok,
            row_counts=row_counts,
            missing_columns=missing_columns,
            parse_errors=errors,
            usable_for_scheduled_routing=required_ok,
        )


def audit_as_dict(path: Path) -> dict:
    return asdict(inspect_gtfs(path))



