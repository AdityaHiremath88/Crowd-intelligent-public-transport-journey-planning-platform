from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from backend_v2.config import DATABASE_PATH, ETM_BUNDLE_PATH, ETM_IMPORT_REPORT_PATH

DATA_PREFIX = "yuktix-october-delhi-clean-data/"
REQUIRED_MEMBERS = {
    f"{DATA_PREFIX}route_demand.parquet",
    f"{DATA_PREFIX}data_quality_report.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_etm_activity(
    *, bundle_path: Path = ETM_BUNDLE_PATH, database_path: Path = DATABASE_PATH,
    report_path: Path = ETM_IMPORT_REPORT_PATH,
) -> dict:
    bundle_path = bundle_path.resolve()
    database_path = database_path.resolve()
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Cleaned October ETM bundle not found: {bundle_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        missing = REQUIRED_MEMBERS - names
        if missing:
            raise ValueError(f"Cleaned ETM archive is missing: {', '.join(sorted(missing))}")
        quality = json.loads(archive.read(f"{DATA_PREFIX}data_quality_report.json"))
        quality_meta = quality.get("dataset_quality", {})
        if quality_meta.get("dataset_rows") != quality.get("table_row_counts", {}).get("etm_records"):
            raise ValueError("ETM quality report has inconsistent source row counts.")
        with tempfile.TemporaryDirectory(prefix="yuktix-v2-etm-") as temp_dir:
            parquet_path = Path(temp_dir) / "route_demand.parquet"
            parquet_path.write_bytes(archive.read(f"{DATA_PREFIX}route_demand.parquet"))
            parquet_sql_path = str(parquet_path).replace("'", "''")
            con = duckdb.connect(str(database_path))
            try:
                columns = {row[0] for row in con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{parquet_sql_path}')"
                ).fetchall()}
                required_columns = {
                    "route", "service_date", "transaction_hour", "day_of_week",
                    "passenger_volume", "transaction_count",
                }
                if not required_columns.issubset(columns):
                    raise ValueError(f"route_demand.parquet is missing columns: {sorted(required_columns - columns)}")
                con.execute("BEGIN TRANSACTION")
                con.execute(f"""
                    CREATE OR REPLACE TABLE etm_route_activity AS
                    SELECT CAST(route AS VARCHAR) AS route_label,
                           CAST(service_date AS DATE) AS service_date,
                           CAST(transaction_hour AS INTEGER) AS transaction_hour,
                           CAST(day_of_week AS INTEGER) AS day_of_week,
                           CAST(passenger_volume AS BIGINT) AS passenger_volume,
                           CAST(transaction_count AS BIGINT) AS transaction_count
                    FROM read_parquet('{parquet_sql_path}')
                """)
                counts = con.execute("""
                    SELECT count(*), min(service_date), max(service_date), count(DISTINCT route_label)
                    FROM etm_route_activity
                """).fetchone()
                if counts[0] != quality["table_row_counts"]["route_demand"]:
                    raise ValueError("Imported ETM activity row count does not match the quality report.")
                con.execute("""
                    CREATE TABLE IF NOT EXISTS etm_import_metadata (
                        imported_at TIMESTAMPTZ, source_file VARCHAR, source_sha256 VARCHAR,
                        source_rows BIGINT, activity_rows BIGINT, date_start DATE, date_end DATE,
                        source_timezone VARCHAR, timestamp_semantics VARCHAR,
                        exact_route_label_matches INTEGER, gtfs_route_labels INTEGER,
                        etm_route_labels INTEGER, limitations_json JSON
                    )
                """)
                con.execute("DELETE FROM etm_import_metadata")
                route_counts = con.execute("""
                    SELECT count(DISTINCT e.route_label),
                           count(DISTINCT CASE WHEN EXISTS (
                               SELECT 1 FROM routes r WHERE r.route_short_name = e.route_label
                           ) THEN e.route_label END),
                           (SELECT count(DISTINCT route_short_name) FROM routes
                            WHERE route_short_name IS NOT NULL AND route_short_name <> '')
                    FROM etm_route_activity e
                """).fetchone()
                limitations = [
                    "created_at is ticket transaction time, not confirmed boarding time.",
                    "Exact ETM route-label to GTFS route_short_name matches are candidates, not validated route or direction mappings.",
                    "No trip linkage, observed occupancy, passenger capacity, or complete rider coverage is available.",
                    "Historical ticket activity is not physical crowding and is not live data.",
                ]
                con.execute("""
                    INSERT INTO etm_import_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    datetime.now(UTC), bundle_path.name, _sha256(bundle_path),
                    quality_meta["dataset_rows"], counts[0], counts[1], counts[2],
                    quality_meta.get("timezone", "Asia/Kolkata"),
                    quality_meta.get("timestamp_semantics", "unknown"),
                    route_counts[1], route_counts[2], route_counts[0],
                    json.dumps(limitations),
                ])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            finally:
                con.close()

    report = {
        "status": "imported",
        "imported_at_utc": datetime.now(UTC).isoformat(),
        "source_file": bundle_path.name,
        "source_sha256": _sha256(bundle_path),
        "source_rows": quality_meta["dataset_rows"],
        "activity_rows": counts[0],
        "date_start": str(counts[1]),
        "date_end": str(counts[2]),
        "distinct_route_labels": counts[3],
        "exact_route_label_matches": route_counts[1],
        "gtfs_route_labels": route_counts[2],
        "etm_route_labels": route_counts[0],
        "limitations": limitations,
    }
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import October ETM route-hour activity into Yuktix v2.")
    parser.add_argument("--zip", type=Path, default=ETM_BUNDLE_PATH)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--report", type=Path, default=ETM_IMPORT_REPORT_PATH)
    args = parser.parse_args()
    print(json.dumps(import_etm_activity(
        bundle_path=args.zip, database_path=args.database, report_path=args.report,
    ), indent=2))


if __name__ == "__main__":
    main()
