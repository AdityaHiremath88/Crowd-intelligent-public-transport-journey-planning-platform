from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.config import DATABASE_PATH


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def export_vehicle_known_subset(
    *, database: Path, output_dir: Path, make_zip: bool = False, overwrite: bool = False
) -> dict:
    if not database.is_file():
        raise FileNotFoundError(f"Processed ETM database not found: {database}")
    output_dir = output_dir.resolve()
    zip_path = output_dir.with_suffix(".zip")
    expected_names = {
        "vehicle_known_ticket_records.parquet",
        "vehicle_route_hourly_activity.parquet",
        "subset_report.json",
        "README.md",
    }
    existing = {path.name for path in output_dir.iterdir()} if output_dir.exists() else set()
    conflicts = existing & expected_names
    if conflicts and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite {', '.join(sorted(conflicts))}; pass --overwrite to replace generated files."
        )
    if make_zip and zip_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {zip_path}; pass --overwrite to replace it.")
    output_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(database.resolve()), read_only=True)
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        required = {"etm_records", "data_quality"}
        if not required.issubset(tables):
            raise ValueError(f"Database is missing required ETM tables: {', '.join(sorted(required - tables))}")

        source_columns = [row[0] for row in con.execute("DESCRIBE data_quality").fetchall()]
        source_row = con.execute(
            "SELECT * FROM data_quality WHERE dataset_name='etm' LIMIT 1"
        ).fetchone()
        if source_row is None:
            raise ValueError("ETM data-quality provenance row is missing")
        source = dict(zip(source_columns, source_row, strict=True))
        total = con.execute("SELECT count(*) FROM etm_records").fetchone()[0]
        missing_vehicle = con.execute(
            "SELECT count(*) FROM etm_records WHERE vehicle_number IS NULL OR trim(vehicle_number)=''"
        ).fetchone()[0]
        retained = total - missing_vehicle
        if retained == 0:
            raise ValueError("No ETM records have a vehicle number")
        distinct_vehicles, distinct_routes, first_date, last_date = con.execute(
            """SELECT count(DISTINCT vehicle_number), count(DISTINCT route),
                      min(transaction_date), max(transaction_date)
               FROM etm_records
               WHERE vehicle_number IS NOT NULL AND trim(vehicle_number)<>''"""
        ).fetchone()

        records_path = output_dir / "vehicle_known_ticket_records.parquet"
        con.execute(
            f"""COPY (
                SELECT row_number() OVER (
                    ORDER BY created_at, vehicle_number, route, start_stop_name,
                             end_stop_name, passenger_count, amount, ticket_type_id, is_ac
                ) AS synthetic_row_id, *
                FROM etm_records
                WHERE vehicle_number IS NOT NULL AND trim(vehicle_number)<>''
            ) TO '{sql_path(records_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )

        activity_path = output_dir / "vehicle_route_hourly_activity.parquet"
        con.execute(
            f"""COPY (
                SELECT vehicle_number, route, transaction_date, transaction_hour,
                       sum(passenger_count)::BIGINT AS recorded_passenger_ticket_volume,
                       count(*)::BIGINT AS ticket_transaction_count,
                       count(DISTINCT start_stop_name)::INTEGER AS distinct_start_labels,
                       count(DISTINCT end_stop_name)::INTEGER AS distinct_end_labels
                FROM etm_records
                WHERE vehicle_number IS NOT NULL AND trim(vehicle_number)<>''
                GROUP BY vehicle_number, route, transaction_date, transaction_hour
            ) TO '{sql_path(activity_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
        activity_rows = con.execute(
            """SELECT count(*) FROM (
                SELECT vehicle_number, route, transaction_date, transaction_hour
                FROM etm_records
                WHERE vehicle_number IS NOT NULL AND trim(vehicle_number)<>''
                GROUP BY ALL
            )"""
        ).fetchone()[0]
    finally:
        con.close()

    report = {
        "title": "October ETM subset with vehicle number present",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_file": source.get("source_file"),
        "source_sha256": source.get("source_sha256"),
        "source_size_bytes": source.get("source_size_bytes"),
        "total_source_rows": total,
        "rows_missing_vehicle_number_removed": missing_vehicle,
        "rows_retained_with_vehicle_number": retained,
        "retained_fraction": round(retained / total, 6),
        "distinct_vehicle_numbers": distinct_vehicles,
        "distinct_non_null_route_labels": distinct_routes,
        "date_start": first_date.isoformat() if first_date else None,
        "date_end": last_date.isoformat() if last_date else None,
        "vehicle_route_date_hour_aggregate_rows": activity_rows,
        "synthetic_row_id_note": (
            "Export-only ordinal for referring to a row in this file. It is not a source ticket ID, "
            "trip ID, or bus-run ID and must not be used to join a ticket to a GTFS trip."
        ),
        "limitations": [
            "Vehicle-number filtering supports exploratory grouping but does not identify individual bus trips.",
            "A vehicle can serve multiple trips or routes in a day; created_at is transaction time, not verified boarding time.",
            "ETM stop labels have not been reviewed against GTFS stop IDs; ticket destinations are not confirmed alightings.",
            "This subset is ticket activity, not validated trip-level load or physical crowding.",
            "Rows without vehicle numbers were omitted from this export only; retain the full dataset for route-time analyses.",
        ],
    }
    report_path = output_dir / "subset_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    readme = """# October ETM subset with vehicle number present

This derived export excludes rows with a null or blank `vehicle_number`; it does not modify the source archive or the full cleaned dataset.

## Files

- `vehicle_known_ticket_records.parquet`: normalized ETM rows plus `synthetic_row_id`, an export-only ordinal. It is not a ticket or trip identifier.
- `vehicle_route_hourly_activity.parquet`: aggregates by vehicle, ETM route label, transaction date, and transaction hour.
- `subset_report.json`: source provenance, row counts, and limitations.

Vehicle numbers support exploratory activity grouping, but they do not identify an individual scheduled trip. `created_at` is ticket transaction time, not verified boarding time. Do not present these outputs as physical occupancy or crowd levels. Use the full ETM dataset, including rows without vehicle numbers, for route-and-time ticket activity analysis.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    if make_zip:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(output_dir.iterdir()):
                if path.is_file() and path.name in expected_names:
                    archive.write(path, arcname=f"{output_dir.name}/{path.name}")
    return {
        **report,
        "output_directory": str(output_dir),
        "zip_path": str(zip_path) if make_zip else None,
        "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest() if make_zip else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export ETM records with a known vehicle number and vehicle-route-hour aggregates."
    )
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip", action="store_true", help="Also create a ZIP beside the output directory.")
    parser.add_argument("--overwrite", action="store_true", help="Replace generated files in the output directory.")
    args = parser.parse_args()
    result = export_vehicle_known_subset(
        database=args.database, output_dir=args.output_dir, make_zip=args.zip, overwrite=args.overwrite
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
