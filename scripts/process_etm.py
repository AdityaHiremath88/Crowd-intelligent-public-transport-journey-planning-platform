from __future__ import annotations

import argparse
import hashlib
import json
from time import perf_counter
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np

from app.config import DATABASE_PATH, ETM_CSV_PATH, PROJECT_ROOT
from app.data_pipeline.run_metadata import ensure_pipeline_run_table, new_run_id

REQUIRED_COLUMNS = {
    "passenger_count", "amount", "vehicle_number", "ticket_type_id", "end_stop_name",
    "route", "start_stop_name", "created_at", "is_ac",
}
ETM_SCHEMA_VERSION = "1.1"
ETM_PIPELINE_VERSION = "0.2.0"


def bootstrap_mean_interval(values: list[float], *, seed: int, resamples: int = 20_000) -> list[float] | None:
    """Percentile bootstrap interval over independent day-level observations; requires >=3 days."""
    if len(values) < 3 or resamples < 1:
        return None
    observations = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=float)
    for index in range(resamples):
        means[index] = rng.choice(observations, size=len(observations), replace=True).mean()
    return [float(value) for value in np.quantile(means, [0.025, 0.975])]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_etm(
    csv_path: Path = ETM_CSV_PATH,
    database_path: Path = DATABASE_PATH,
    report_path: Path | None = None,
) -> dict:
    run_started = perf_counter()
    run_id = new_run_id()
    if not csv_path.is_file():
        raise FileNotFoundError(f"ETM CSV not found: {csv_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database_path))
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("SET timezone='Asia/Kolkata'")
        con.from_csv_auto(str(csv_path), sample_size=-1).create("etm_source")
        columns = {row[0] for row in con.execute("DESCRIBE etm_source").fetchall()}
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            raise ValueError(f"ETM file is missing required columns: {', '.join(missing_columns)}")

        # Preserve every source row. NULL-like text is normalized only in derived fields.
        con.execute("""
            CREATE OR REPLACE TABLE etm_records AS
            SELECT
                passenger_count,
                amount,
                CASE WHEN upper(trim(vehicle_number)) IN ('', 'NULL', 'NA', 'N/A') THEN NULL
                     ELSE upper(trim(vehicle_number)) END AS vehicle_number,
                ticket_type_id,
                CASE WHEN upper(trim(end_stop_name)) IN ('', 'NULL', 'NA', 'N/A') THEN NULL
                     ELSE regexp_replace(trim(end_stop_name), '\\s+', ' ', 'g') END AS end_stop_name,
                CASE WHEN upper(trim(route)) IN ('', 'NULL', 'NA', 'N/A') THEN NULL
                     ELSE regexp_replace(upper(trim(route)), '\\s+', '', 'g') END AS route,
                CASE WHEN upper(trim(start_stop_name)) IN ('', 'NULL', 'NA', 'N/A') THEN NULL
                     ELSE regexp_replace(trim(start_stop_name), '\\s+', ' ', 'g') END AS start_stop_name,
                created_at,
                is_ac,
                timezone('Asia/Kolkata', created_at) AS transaction_local_time,
                date(timezone('Asia/Kolkata', created_at)) AS transaction_date,
                hour(timezone('Asia/Kolkata', created_at)) AS transaction_hour,
                dayofweek(timezone('Asia/Kolkata', created_at)) AS transaction_weekday_sunday_zero
            FROM etm_source
        """)

        aggregate = con.execute("""
            SELECT
                count(*) AS dataset_rows,
                min(created_at) AS dataset_min_timestamp,
                max(created_at) AS dataset_max_timestamp,
                count(DISTINCT route) AS distinct_routes,
                count(DISTINCT vehicle_number) AS distinct_vehicles,
                count(DISTINCT start_stop_name) AS distinct_start_stops,
                count(DISTINCT end_stop_name) AS distinct_end_stops,
                count(*) FILTER (WHERE vehicle_number IS NULL) AS null_vehicle_rows,
                count(*) FILTER (WHERE passenger_count <= 0 OR passenger_count IS NULL) AS invalid_passenger_rows,
                min(passenger_count) AS passenger_count_min,
                max(passenger_count) AS passenger_count_max,
                avg(passenger_count) AS passenger_count_mean,
                sum(passenger_count) AS passenger_volume_total,
                sum(amount) AS amount_total,
                count(*) FILTER (WHERE amount < 0 OR amount IS NULL) AS invalid_amount_rows,
                count(*) FILTER (WHERE start_stop_name IS NULL) AS null_start_stop_rows,
                count(*) FILTER (WHERE end_stop_name IS NULL) AS null_end_stop_rows,
                count(*) FILTER (WHERE route IS NULL) AS null_route_rows
            FROM etm_records
        """).fetchone()
        keys = [item[0] for item in con.description]
        quality = dict(zip(keys, aggregate, strict=True))
        quality["dataset_name"] = "etm"
        quality["source_file"] = csv_path.name
        quality["source_sha256"] = sha256_file(csv_path)
        quality["source_size_bytes"] = csv_path.stat().st_size
        quality["schema_version"] = ETM_SCHEMA_VERSION
        quality["pipeline_version"] = ETM_PIPELINE_VERSION
        quality["timezone"] = "Asia/Kolkata"
        quality["generated_at"] = datetime.now(UTC).isoformat()
        quality["retained_rows"] = quality["dataset_rows"]
        quality["excluded_rows"] = 0
        quality["deduplication"] = "none; source has no defensible transaction identifier"
        quality["timestamp_semantics"] = "created_at treated as ticket transaction timestamp, not boarding time"
        quality["exact_duplicate_rows"] = con.execute("""
            SELECT coalesce(sum(n - 1), 0) FROM (
                SELECT count(*) AS n
                FROM etm_source
                GROUP BY passenger_count, amount, vehicle_number, ticket_type_id,
                         end_stop_name, route, start_stop_name, created_at, is_ac
                HAVING count(*) > 1
            )
        """).fetchone()[0]

        amount_profile = con.execute("""
            SELECT min(amount), max(amount), quantile_cont(amount, [0.5, 0.9, 0.99]),
                   count(*) FILTER (WHERE amount > (SELECT quantile_cont(amount, 0.99) FROM etm_records))
            FROM etm_records
        """).fetchone()
        daily_observations = con.execute("""
            SELECT CASE WHEN dayofweek(transaction_date) IN (0, 6) THEN 'weekend' ELSE 'weekday' END day_type,
                   transaction_date,
                   sum(passenger_count)::DOUBLE passenger_volume,
                   count(*)::DOUBLE transaction_count
            FROM etm_records GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall()
        day_groups = {
            kind: [(float(pax), float(tx)) for observed_kind, _, pax, tx in daily_observations if observed_kind == kind]
            for kind in ("weekday", "weekend")
        }

        con.execute("""
            CREATE OR REPLACE TABLE stop_catalog AS
            SELECT DISTINCT
                'etm_' || substr(sha256(start_stop_name), 1, 16) AS stop_id,
                start_stop_name AS stop_name
            FROM etm_records
            WHERE start_stop_name IS NOT NULL
        """)
        con.execute("""
            CREATE OR REPLACE TABLE stop_demand AS
            SELECT
                'etm_' || substr(sha256(start_stop_name), 1, 16) AS stop_id,
                start_stop_name AS stop_name,
                route,
                transaction_weekday_sunday_zero AS day_of_week,
                transaction_hour,
                transaction_date AS service_date,
                sum(passenger_count)::BIGINT AS passenger_volume,
                count(*)::BIGINT AS transaction_count
            FROM etm_records
            WHERE start_stop_name IS NOT NULL
            GROUP BY ALL
        """)
        con.execute("""
            CREATE OR REPLACE TABLE route_demand AS
            SELECT
                route,
                transaction_date AS service_date,
                transaction_hour,
                transaction_weekday_sunday_zero AS day_of_week,
                sum(passenger_count)::BIGINT AS passenger_volume,
                count(*)::BIGINT AS transaction_count
            FROM etm_records
            WHERE route IS NOT NULL
            GROUP BY ALL
        """)
        con.execute("""
            CREATE OR REPLACE TABLE route_stop_catalog AS
            SELECT DISTINCT route, start_stop_name
            FROM etm_records
            WHERE route IS NOT NULL AND start_stop_name IS NOT NULL
        """)
        con.execute("""
            CREATE OR REPLACE TABLE service_profile AS
            SELECT
                transaction_date AS service_date,
                transaction_hour,
                is_ac,
                ticket_type_id,
                sum(passenger_count)::BIGINT AS passenger_volume,
                count(*)::BIGINT AS transaction_count
            FROM etm_records
            GROUP BY ALL
        """)
        con.execute("""
            CREATE OR REPLACE TABLE daily_demand AS
            SELECT transaction_date AS service_date,
                   sum(passenger_count)::BIGINT AS passenger_volume,
                   count(*)::BIGINT AS transaction_count
            FROM etm_records
            GROUP BY transaction_date
        """)
        con.execute("""
            CREATE OR REPLACE TABLE hourly_demand AS
            SELECT transaction_date AS service_date,
                   transaction_hour,
                   transaction_weekday_sunday_zero AS day_of_week,
                   sum(passenger_count)::BIGINT AS passenger_volume,
                   count(*)::BIGINT AS transaction_count
            FROM etm_records
            GROUP BY ALL
        """)
        con.register("quality_df", __import__("pandas").DataFrame([quality]))
        con.execute("CREATE OR REPLACE TABLE data_quality AS SELECT * FROM quality_df")
        con.unregister("quality_df")
        con.execute("DROP TABLE etm_source")

        ensure_pipeline_run_table(con)
        con.execute(
            """INSERT INTO pipeline_runs (
                   run_id, dataset_name, source_file, source_sha256, source_size_bytes,
                   schema_version, pipeline_version, generated_at, input_rows,
                   retained_rows, excluded_rows, run_status, execution_seconds
               ) VALUES (?, 'etm', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'succeeded', ?)""",
            [
                run_id, csv_path.name, quality["source_sha256"], quality["source_size_bytes"],
                ETM_SCHEMA_VERSION, ETM_PIPELINE_VERSION, quality["generated_at"],
                quality["dataset_rows"], quality["retained_rows"], quality["excluded_rows"],
                perf_counter() - run_started,
            ],
        )

        report = {
            **quality,
            "dataset_min_timestamp": str(quality["dataset_min_timestamp"]),
            "dataset_max_timestamp": str(quality["dataset_max_timestamp"]),
            "table_rows": {
                "etm_records": quality["dataset_rows"],
                "stop_catalog": con.execute("SELECT count(*) FROM stop_catalog").fetchone()[0],
                "stop_demand": con.execute("SELECT count(*) FROM stop_demand").fetchone()[0],
                "route_demand": con.execute("SELECT count(*) FROM route_demand").fetchone()[0],
                "route_stop_catalog": con.execute("SELECT count(*) FROM route_stop_catalog").fetchone()[0],
                "service_profile": con.execute("SELECT count(*) FROM service_profile").fetchone()[0],
                "daily_demand": con.execute("SELECT count(*) FROM daily_demand").fetchone()[0],
                "hourly_demand": con.execute("SELECT count(*) FROM hourly_demand").fetchone()[0],
            },
            "hourly_transaction_volume": con.execute("""
                SELECT transaction_hour, sum(passenger_volume)::BIGINT passenger_volume,
                       sum(transaction_count)::BIGINT transaction_count
                FROM stop_demand GROUP BY 1 ORDER BY 1
            """).fetchall(),
            "weekday_weekend_daily_averages": con.execute("""
                WITH daily AS (
                    SELECT transaction_date,
                           sum(passenger_count)::DOUBLE AS passenger_volume,
                           count(*)::DOUBLE AS transaction_count
                    FROM etm_records GROUP BY 1
                )
                SELECT CASE WHEN dayofweek(transaction_date) IN (0, 6) THEN 'weekend' ELSE 'weekday' END AS day_type,
                       count(*) AS observed_days,
                       avg(passenger_volume) AS avg_daily_passenger_volume,
                       avg(transaction_count) AS avg_daily_transaction_count
                FROM daily GROUP BY 1 ORDER BY 1
            """).fetchall(),
            "weekday_weekend_bootstrap_95pct": {
                kind: {
                    "observed_days": len(values),
                    "passenger_volume_mean_interval": bootstrap_mean_interval([item[0] for item in values], seed=20261117),
                    "transaction_count_mean_interval": bootstrap_mean_interval([item[1] for item in values], seed=20261118),
                    "method": "percentile bootstrap resampling calendar days with replacement; descriptive only",
                }
                for kind, values in day_groups.items()
            },
            "amount_distribution": {
                "min": amount_profile[0],
                "max": amount_profile[1],
                "p50_p90_p99": amount_profile[2],
                "count_above_p99": amount_profile[3],
                "semantic_note": "amount units and fare/refund semantics are not documented",
            },
            "weekly_ticket_volume": con.execute("""
                SELECT date_trunc('week', transaction_date)::DATE AS week_start,
                       sum(passenger_count)::BIGINT AS passenger_volume,
                       count(*)::BIGINT AS transaction_count
                FROM etm_records GROUP BY 1 ORDER BY 1
            """).fetchall(),
            "passenger_count_distribution": con.execute("""
                SELECT passenger_count, count(*)::BIGINT AS transaction_count
                FROM etm_records GROUP BY 1 ORDER BY 1
            """).fetchall(),
            "ac_flag_values": con.execute("""
                SELECT is_ac, count(*)::BIGINT AS transaction_count
                FROM etm_records GROUP BY 1 ORDER BY 1
            """).fetchall(),
            "ticket_type_values": con.execute("""
                SELECT ticket_type_id, count(*)::BIGINT AS transaction_count
                FROM etm_records GROUP BY 1 ORDER BY transaction_count DESC
            """).fetchall(),
            "peak_window_daily_averages": con.execute("""
                WITH daily_hour AS (
                    SELECT transaction_date, transaction_hour,
                           sum(passenger_count)::DOUBLE AS passenger_volume,
                           count(*)::DOUBLE AS transaction_count
                    FROM etm_records GROUP BY 1, 2
                ), daily AS (
                    SELECT transaction_date,
                           sum(passenger_volume) FILTER (WHERE transaction_hour BETWEEN 6 AND 9) AS morning_passenger_volume,
                           sum(passenger_volume) FILTER (WHERE transaction_hour BETWEEN 16 AND 19) AS evening_passenger_volume,
                           sum(transaction_count) FILTER (WHERE transaction_hour BETWEEN 6 AND 9) AS morning_transactions,
                           sum(transaction_count) FILTER (WHERE transaction_hour BETWEEN 16 AND 19) AS evening_transactions
                    FROM daily_hour GROUP BY 1
                )
                SELECT avg(morning_passenger_volume), avg(evening_passenger_volume),
                       avg(morning_transactions), avg(evening_transactions) FROM daily
            """).fetchone(),
            "top_recorded_routes": con.execute("""
                SELECT route, sum(passenger_count)::BIGINT AS passenger_volume,
                       count(*)::BIGINT AS transaction_count
                FROM etm_records WHERE route IS NOT NULL GROUP BY 1
                ORDER BY passenger_volume DESC LIMIT 10
            """).fetchall(),
            "top_ticket_start_labels": con.execute("""
                SELECT start_stop_name, sum(passenger_count)::BIGINT AS passenger_volume,
                       count(*)::BIGINT AS transaction_count
                FROM etm_records WHERE start_stop_name IS NOT NULL GROUP BY 1
                ORDER BY passenger_volume DESC LIMIT 10
            """).fetchall(),
            "validation_scope": "descriptive within-month checks; no predictive holdout or occupancy ground truth",
            "source_sha256": quality["source_sha256"],
            "source_size_bytes": quality["source_size_bytes"],
            "schema_version": ETM_SCHEMA_VERSION,
            "pipeline_version": ETM_PIPELINE_VERSION,
            "run_id": run_id,
            "execution_seconds": round(perf_counter() - run_started, 3),
            "processing_timezone": "Asia/Kolkata",
            "caveats": [
                "Passenger volume is the sum of the passenger_count field, not a physical queue count.",
                "created_at is transaction time; this report does not treat it as boarding time.",
                "ETM start/end labels have not yet been verified against GTFS stop IDs or ticket semantics.",
                "No trip-level onboard load is produced because there is no reliable individual trip identifier.",
            ],
        }
        report["execution_seconds"] = round(perf_counter() - run_started, 3)
        con.execute(
            "UPDATE pipeline_runs SET execution_seconds=? WHERE run_id=?",
            [report["execution_seconds"], run_id],
        )
        output = report_path or (PROJECT_ROOT / "outputs" / "etm_data_quality.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        con.execute("COMMIT")
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return report
    except Exception:
        try:
            con.execute("ROLLBACK")
        except duckdb.Error:
            pass
        raise
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and aggregate Delhi ETM ticket records with DuckDB.")
    parser.add_argument("--csv", type=Path, default=ETM_CSV_PATH)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    args = parser.parse_args()
    report = process_etm(args.csv.resolve(), args.database.resolve())
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()



