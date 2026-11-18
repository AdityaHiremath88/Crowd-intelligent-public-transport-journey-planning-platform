from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

import duckdb

from app.config import DATABASE_PATH, GTFS_ZIP_PATH, PROJECT_ROOT
from app.data_pipeline.gtfs_loader import inspect_gtfs
from app.data_pipeline.run_metadata import ensure_pipeline_run_table, new_run_id

GTFS_SCHEMA_VERSION = "1.1"
GTFS_PIPELINE_VERSION = "0.2.0"
MAP_ONLY_ISSUES = {"invalid_stop_coordinates", "invalid_shape_coordinates", "shape_reference_missing", "invalid_shape_sequence", "duplicate_shape_sequence"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_gtfs(
    zip_path: Path = GTFS_ZIP_PATH,
    database_path: Path = DATABASE_PATH,
    report_path: Path | None = None,
) -> dict:
    run_started = perf_counter()
    run_id = new_run_id()
    audit = inspect_gtfs(zip_path)
    if not audit.usable_for_scheduled_routing:
        raise ValueError(f"GTFS feed is incomplete or invalid: {audit}")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database_path))
    try:
        con.execute("BEGIN TRANSACTION")
        with tempfile.TemporaryDirectory(prefix="crowdwise_gtfs_") as tmp:
            staging = Path(tmp)
            with ZipFile(zip_path) as archive:
                for member in archive.namelist():
                    if (
                        Path(member).name.lower().endswith(".txt")
                        and not Path(member).name.startswith("._")
                        and not member.startswith("__MACOSX/")
                    ):
                        target = staging / Path(member).name.lower()
                        with archive.open(member) as source, target.open("wb") as output:
                            output.write(source.read())
            loaded: dict[str, int] = {}
            for table_file in sorted(staging.glob("*.txt")):
                table_name = f"gtfs_{table_file.stem.lower()}"
                quoted_table = '"' + table_name.replace('"', '""') + '"'
                csv_path = str(table_file.resolve()).replace("'", "''")
                con.execute(
                    f"CREATE OR REPLACE TABLE {quoted_table} AS "
                    f"SELECT * FROM read_csv_auto('{csv_path}', all_varchar=true, header=true)"
                )
                loaded[table_file.name] = con.execute(f"SELECT count(*) FROM {quoted_table}").fetchone()[0]

        calendar_service_parts = []
        if "calendar.txt" in loaded:
            calendar_service_parts.append("SELECT service_id FROM gtfs_calendar")
        if "calendar_dates.txt" in loaded:
            calendar_service_parts.append("SELECT service_id FROM gtfs_calendar_dates")
        calendar_service_sql = " UNION ".join(calendar_service_parts)
        calendar_date_issue_sql = (
            "SELECT count(*) FROM gtfs_calendar_dates WHERE "
            "try_strptime(date, '%Y%m%d') IS NULL OR exception_type NOT IN ('1', '2')"
            if "calendar_dates.txt" in loaded else "SELECT 0"
        )
        calendar_range_issue_sql = (
            "SELECT count(*) FROM gtfs_calendar WHERE "
            "try_strptime(start_date, '%Y%m%d') IS NULL OR "
            "try_strptime(end_date, '%Y%m%d') IS NULL OR "
            "try_strptime(start_date, '%Y%m%d') > try_strptime(end_date, '%Y%m%d')"
            if "calendar.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql = {
            "invalid_stop_coordinates": (
                "SELECT count(*) FROM gtfs_stops WHERE "
                "try_cast(stop_lat AS DOUBLE) IS NULL OR try_cast(stop_lon AS DOUBLE) IS NULL OR "
                "try_cast(stop_lat AS DOUBLE) NOT BETWEEN -90 AND 90 OR "
                "try_cast(stop_lon AS DOUBLE) NOT BETWEEN -180 AND 180"
            ),
            "duplicate_stop_id": "SELECT count(*) FROM (SELECT stop_id FROM gtfs_stops GROUP BY stop_id HAVING count(*) > 1)",
            "duplicate_route_id": "SELECT count(*) FROM (SELECT route_id FROM gtfs_routes GROUP BY route_id HAVING count(*) > 1)",
            "duplicate_trip_id": "SELECT count(*) FROM (SELECT trip_id FROM gtfs_trips GROUP BY trip_id HAVING count(*) > 1)",
            "invalid_route_type": (
                "SELECT count(*) FROM gtfs_routes WHERE "
                "try_cast(route_type AS INTEGER) IS NULL OR try_cast(route_type AS INTEGER) < 0"
            ),
            "invalid_stop_sequence": (
                "SELECT count(*) FROM gtfs_stop_times WHERE "
                "try_cast(stop_sequence AS INTEGER) IS NULL OR try_cast(stop_sequence AS INTEGER) < 0"
            ),
            "trips_without_stop_times": (
                "SELECT count(*) FROM gtfs_trips t LEFT JOIN "
                "(SELECT DISTINCT trip_id FROM gtfs_stop_times) st USING (trip_id) WHERE st.trip_id IS NULL"
            ),
            "invalid_service_weekday_flag": (
                "SELECT count(*) FROM gtfs_calendar WHERE "
                "monday NOT IN ('0','1') OR tuesday NOT IN ('0','1') OR wednesday NOT IN ('0','1') OR "
                "thursday NOT IN ('0','1') OR friday NOT IN ('0','1') OR saturday NOT IN ('0','1') OR sunday NOT IN ('0','1')"
            ) if "calendar.txt" in loaded else "SELECT 0",
            "decreasing_trip_times": """SELECT count(*) FROM (
                SELECT trip_id, stop_sequence, arrival_seconds,
                       lag(departure_seconds) OVER (PARTITION BY trip_id ORDER BY try_cast(stop_sequence AS INTEGER)) previous_departure
                FROM (
                    SELECT trip_id, stop_sequence,
                           (try_cast(split_part(arrival_time, ':', 1) AS BIGINT) * 3600 + try_cast(split_part(arrival_time, ':', 2) AS BIGINT) * 60 + try_cast(split_part(arrival_time, ':', 3) AS BIGINT)) arrival_seconds,
                           (try_cast(split_part(departure_time, ':', 1) AS BIGINT) * 3600 + try_cast(split_part(departure_time, ':', 2) AS BIGINT) * 60 + try_cast(split_part(departure_time, ':', 3) AS BIGINT)) departure_seconds
                    FROM gtfs_stop_times
                )
            ) WHERE previous_departure > arrival_seconds""",
        }
        optional_issue_sql["invalid_shape_coordinates"] = (
            "SELECT count(*) FROM gtfs_shapes WHERE "
            "try_cast(shape_pt_lat AS DOUBLE) IS NULL OR try_cast(shape_pt_lon AS DOUBLE) IS NULL OR "
            "try_cast(shape_pt_lat AS DOUBLE) NOT BETWEEN -90 AND 90 OR "
            "try_cast(shape_pt_lon AS DOUBLE) NOT BETWEEN -180 AND 180"
            if "shapes.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["shape_reference_missing"] = (
            "SELECT count(*) FROM gtfs_trips t LEFT JOIN (SELECT DISTINCT shape_id FROM gtfs_shapes) s USING (shape_id) "
            "WHERE coalesce(t.shape_id, '') <> '' AND s.shape_id IS NULL"
            if "shapes.txt" in loaded and "shape_id" in {row[0] for row in con.execute("DESCRIBE gtfs_trips").fetchall()}
            else "SELECT 0"
        )
        optional_issue_sql["invalid_shape_sequence"] = (
            "SELECT count(*) FROM gtfs_shapes WHERE try_cast(shape_pt_sequence AS INTEGER) IS NULL OR try_cast(shape_pt_sequence AS INTEGER) <= 0"
            if "shapes.txt" in loaded else "SELECT 0"
        )
        transfer_columns = (
            {row[0] for row in con.execute("DESCRIBE gtfs_transfers").fetchall()}
            if "transfers.txt" in loaded else set()
        )
        transfer_min_time_check = (
            "(x.transfer_type = '2' AND (x.min_transfer_time IS NULL OR try_cast(x.min_transfer_time AS INTEGER) IS NULL OR try_cast(x.min_transfer_time AS INTEGER) < 0))"
            if "min_transfer_time" in transfer_columns else "(x.transfer_type = '2')"
        )
        optional_issue_sql["invalid_transfer_reference"] = (
            "SELECT count(*) FROM gtfs_transfers x "
            "LEFT JOIN gtfs_stops a ON a.stop_id=x.from_stop_id "
            "LEFT JOIN gtfs_stops b ON b.stop_id=x.to_stop_id "
            "WHERE a.stop_id IS NULL OR b.stop_id IS NULL OR "
            + transfer_min_time_check
            if "transfers.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["invalid_transfer_type"] = (
            "SELECT count(*) FROM gtfs_transfers WHERE transfer_type NOT IN ('0','1','2','3','4','5')"
            if "transfers.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["transfer_rules_present_unsupported"] = (
            "SELECT count(*) FROM gtfs_transfers" if "transfers.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["invalid_frequency_definition"] = (
            "SELECT count(*) FROM gtfs_frequencies WHERE "
            "try_cast(headway_secs AS INTEGER) IS NULL OR try_cast(headway_secs AS INTEGER) <= 0 OR "
            "NOT regexp_full_match(start_time, '[0-9]+:[0-5][0-9]:[0-5][0-9]') OR "
            "NOT regexp_full_match(end_time, '[0-9]+:[0-5][0-9]:[0-5][0-9]') OR "
            "try_cast(headway_secs AS INTEGER) <= 0 OR "
            "try_cast(split_part(start_time, ':', 1) AS BIGINT) * 3600 + try_cast(split_part(start_time, ':', 2) AS BIGINT) * 60 + try_cast(split_part(start_time, ':', 3) AS BIGINT) >= "
            "try_cast(split_part(end_time, ':', 1) AS BIGINT) * 3600 + try_cast(split_part(end_time, ':', 2) AS BIGINT) * 60 + try_cast(split_part(end_time, ':', 3) AS BIGINT)"
            if "frequencies.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["frequency_service_present_unsupported"] = (
            "SELECT count(*) FROM gtfs_frequencies" if "frequencies.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["frequency_trip_reference_missing"] = (
            "SELECT count(*) FROM gtfs_frequencies f LEFT JOIN gtfs_trips t USING(trip_id) WHERE t.trip_id IS NULL"
            if "frequencies.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["arrival_after_departure"] = """SELECT count(*) FROM gtfs_stop_times
            WHERE (try_cast(split_part(arrival_time, ':', 1) AS BIGINT) * 3600 + try_cast(split_part(arrival_time, ':', 2) AS BIGINT) * 60 + try_cast(split_part(arrival_time, ':', 3) AS BIGINT)) >
                  (try_cast(split_part(departure_time, ':', 1) AS BIGINT) * 3600 + try_cast(split_part(departure_time, ':', 2) AS BIGINT) * 60 + try_cast(split_part(departure_time, ':', 3) AS BIGINT))"""
        optional_issue_sql["duplicate_calendar_service_id"] = (
            "SELECT count(*) FROM (SELECT service_id FROM gtfs_calendar GROUP BY service_id HAVING count(*) > 1)"
            if "calendar.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["duplicate_calendar_exception"] = (
            "SELECT count(*) FROM (SELECT service_id, date FROM gtfs_calendar_dates GROUP BY service_id, date HAVING count(*) > 1)"
            if "calendar_dates.txt" in loaded else "SELECT 0"
        )
        optional_issue_sql["duplicate_shape_sequence"] = (
            "SELECT count(*) FROM (SELECT shape_id, shape_pt_sequence FROM gtfs_shapes GROUP BY shape_id, shape_pt_sequence HAVING count(*) > 1)"
            if "shapes.txt" in loaded else "SELECT 0"
        )
        issues = {
            "stop_time_missing_trip": con.execute("""
                SELECT count(*) FROM gtfs_stop_times st
                LEFT JOIN gtfs_trips t USING (trip_id) WHERE t.trip_id IS NULL
            """).fetchall()[0][0],
            "stop_time_missing_stop": con.execute("""
                SELECT count(*) FROM gtfs_stop_times st
                LEFT JOIN gtfs_stops s USING (stop_id) WHERE s.stop_id IS NULL
            """).fetchall()[0][0],
            "trip_missing_route": con.execute("""
                SELECT count(*) FROM gtfs_trips t
                LEFT JOIN gtfs_routes r USING (route_id) WHERE r.route_id IS NULL
            """).fetchall()[0][0],
            "stop_times_without_sequence": con.execute("""
                SELECT count(*) FROM gtfs_stop_times
                WHERE try_cast(stop_sequence AS INTEGER) IS NULL
            """).fetchall()[0][0],
            "trip_missing_service_calendar": con.execute(f"""
                SELECT count(*) FROM gtfs_trips t
                LEFT JOIN ({calendar_service_sql}) c USING (service_id)
                WHERE c.service_id IS NULL
            """).fetchall()[0][0],
            "duplicate_trip_stop_sequence": con.execute("""
                SELECT count(*) FROM (
                    SELECT trip_id, stop_sequence FROM gtfs_stop_times
                    GROUP BY trip_id, stop_sequence HAVING count(*) > 1
                )
            """).fetchall()[0][0],
            "invalid_stop_time_format": con.execute("""
                SELECT count(*) FROM gtfs_stop_times
                WHERE NOT regexp_full_match(arrival_time, '[0-9]+:[0-5][0-9]:[0-5][0-9]')
                   OR NOT regexp_full_match(departure_time, '[0-9]+:[0-5][0-9]:[0-5][0-9]')
            """).fetchall()[0][0],
            "invalid_service_calendar_date": con.execute(f"""
                {calendar_range_issue_sql}
            """).fetchall()[0][0],
            "invalid_calendar_exception": con.execute(f"""
                {calendar_date_issue_sql}
            """).fetchall()[0][0],
            **{
                name: con.execute(sql).fetchall()[0][0]
                for name, sql in optional_issue_sql.items()
            },
        }
        service_window = con.execute(f"""
            SELECT min(service_date), max(service_date) FROM (
                {"SELECT try_strptime(start_date, '%Y%m%d')::DATE service_date FROM gtfs_calendar UNION ALL SELECT try_strptime(end_date, '%Y%m%d')::DATE FROM gtfs_calendar" if "calendar.txt" in loaded else "SELECT NULL::DATE service_date WHERE FALSE"}
                UNION ALL
                {"SELECT try_strptime(date, '%Y%m%d')::DATE FROM gtfs_calendar_dates" if "calendar_dates.txt" in loaded else "SELECT NULL::DATE WHERE FALSE"}
            )
        """).fetchall()[0]
        source_sha256 = sha256_file(zip_path)
        generated_at = datetime.now(UTC).isoformat()
        result_issue_values = {name: int(value) for name, value in issues.items()}
        schedule_issues = {name: value for name, value in result_issue_values.items() if name not in MAP_ONLY_ISSUES}
        map_issues = {name: result_issue_values[name] for name in MAP_ONLY_ISSUES if name in result_issue_values}
        result = {
            "dataset_name": "gtfs",
            "source_file": zip_path.name,
            "source_sha256": source_sha256,
            "source_size_bytes": zip_path.stat().st_size,
            "schema_version": GTFS_SCHEMA_VERSION,
            "pipeline_version": GTFS_PIPELINE_VERSION,
            "generated_at": generated_at,
            "run_id": run_id,
            "files": audit.files,
            "optional_files": audit.optional_files,
            "row_counts": loaded,
            "issues": issues,
            "usable_for_scheduled_routing": all(value == 0 for value in schedule_issues.values()),
            "usable_for_map": all(value == 0 for value in map_issues.values()),
            "schedule_issues": schedule_issues,
            "map_issues": map_issues,
            "service_start_date": service_window[0],
            "service_end_date": service_window[1],
            "times_are_stored_as_text": True,
            "after_midnight_times": "preserved as HH:MM:SS text; parse with parse_gtfs_time (supports hours >= 24)",
        }
        ensure_pipeline_run_table(con)
        result["execution_seconds"] = round(perf_counter() - run_started, 3)
        con.execute(
            """INSERT INTO pipeline_runs (
                   run_id, dataset_name, source_file, source_sha256, source_size_bytes,
                   schema_version, pipeline_version, generated_at, input_rows,
                   retained_rows, excluded_rows, run_status, execution_seconds
               ) VALUES (?, 'gtfs', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            [
                run_id, zip_path.name, source_sha256, zip_path.stat().st_size,
                GTFS_SCHEMA_VERSION, GTFS_PIPELINE_VERSION, generated_at,
                sum(loaded.values()), sum(loaded.values()),
                "succeeded" if result["usable_for_scheduled_routing"] else "loaded_unusable",
                result["execution_seconds"],
            ],
        )
        con.register("gtfs_quality_df", __import__("pandas").DataFrame([{
            "dataset_name": "gtfs",
            "source_file": zip_path.name,
            "source_sha256": source_sha256,
            "source_size_bytes": zip_path.stat().st_size,
            "schema_version": GTFS_SCHEMA_VERSION,
            "pipeline_version": GTFS_PIPELINE_VERSION,
            "generated_at": generated_at,
            "usable_for_scheduled_routing": result["usable_for_scheduled_routing"],
            "usable_for_map": result["usable_for_map"],
            "service_start_date": service_window[0],
            "service_end_date": service_window[1],
            "total_rows": sum(loaded.values()),
            "issue_json": json.dumps(issues),
        }]))
        con.execute("CREATE OR REPLACE TABLE gtfs_quality AS SELECT * FROM gtfs_quality_df")
        con.unregister("gtfs_quality_df")
        result["execution_seconds"] = round(perf_counter() - run_started, 3)
        con.execute(
            "UPDATE pipeline_runs SET execution_seconds=? WHERE run_id=?",
            [result["execution_seconds"], run_id],
        )
        con.execute("COMMIT")
        output = report_path or (PROJECT_ROOT / "outputs" / "gtfs_validation.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result
    except Exception:
        try:
            con.execute("ROLLBACK")
        except duckdb.Error:
            pass
        raise
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and load a Delhi GTFS static ZIP into DuckDB.")
    parser.add_argument("--zip", type=Path, default=GTFS_ZIP_PATH)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    args = parser.parse_args()
    print(json.dumps(process_gtfs(args.zip.resolve(), args.database.resolve()), indent=2))


if __name__ == "__main__":
    main()



