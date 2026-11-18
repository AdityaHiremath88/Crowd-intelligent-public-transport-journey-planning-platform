from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from app.config import DATABASE_PATH, PROJECT_ROOT


def assess(database_path: Path = DATABASE_PATH, report_path: Path | None = None) -> dict:
    if not database_path.is_file():
        raise FileNotFoundError(f"Processed ETM database not found: {database_path}")
    con = duckdb.connect(str(database_path), read_only=True)
    try:
        available = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "etm_records" not in available:
            raise ValueError("etm_records table is missing; run scripts.process_etm first")
        source_fields = [row[0] for row in con.execute("DESCRIBE etm_records").fetchall()]
        has_trip_id = any(field.casefold() in {"trip_id", "journey_id", "run_id"} for field in source_fields)
        summary = con.execute("""
            WITH vehicle_day AS (
                SELECT vehicle_number, transaction_date,
                       count(*) AS ticket_rows,
                       count(DISTINCT route) AS route_labels,
                       count(DISTINCT start_stop_name) AS start_labels,
                       count(DISTINCT end_stop_name) AS end_labels
                FROM etm_records
                WHERE vehicle_number IS NOT NULL
                GROUP BY 1, 2
            )
            SELECT count(*) AS vehicle_days,
                   count(*) FILTER (WHERE route_labels > 1) AS vehicle_days_multiple_routes,
                   avg(route_labels) AS avg_route_labels_per_vehicle_day,
                   max(ticket_rows) AS max_ticket_rows_per_vehicle_day,
                   avg(start_labels) AS avg_start_labels_per_vehicle_day,
                   avg(end_labels) AS avg_end_labels_per_vehicle_day
            FROM vehicle_day
        """).fetchall()[0]
        gaps = con.execute("""
            WITH ordered AS (
                SELECT vehicle_number, route, transaction_date, transaction_local_time,
                       lag(transaction_local_time) OVER (
                           PARTITION BY vehicle_number, route, transaction_date
                           ORDER BY transaction_local_time
                       ) AS previous_time
                FROM etm_records
                WHERE vehicle_number IS NOT NULL
            ), intervals AS (
                SELECT date_diff('second', previous_time, transaction_local_time) AS seconds
                FROM ordered WHERE previous_time IS NOT NULL
            )
            SELECT count(*) AS adjacent_ticket_pairs,
                   quantile_cont(seconds, [0.5, 0.9, 0.99]) AS gap_seconds_p50_p90_p99,
                   count(*) FILTER (WHERE seconds > 3600) AS pairs_over_one_hour
            FROM intervals WHERE seconds >= 0
        """).fetchall()[0]
        vehicle_row = con.execute("""
            SELECT count(*) AS source_rows,
                   count(*) FILTER (WHERE vehicle_number IS NULL) AS no_vehicle_rows,
                   count(DISTINCT vehicle_number) AS distinct_usable_vehicles
            FROM etm_records
        """).fetchall()[0]
        result = {
            "assessment": "vehicle-and-transaction-time trip-inference feasibility",
            "source_rows": vehicle_row[0],
            "no_vehicle_rows": vehicle_row[1],
            "distinct_usable_vehicles": vehicle_row[2],
            "vehicle_days_with_vehicle": summary[0],
            "vehicle_days_with_multiple_route_labels": summary[1],
            "avg_route_labels_per_vehicle_day": summary[2],
            "max_ticket_rows_per_vehicle_day": summary[3],
            "avg_start_labels_per_vehicle_day": summary[4],
            "avg_end_labels_per_vehicle_day": summary[5],
            "adjacent_vehicle_route_day_ticket_pairs": gaps[0],
            "transaction_gap_seconds_p50_p90_p99": gaps[1],
            "pairs_with_gap_over_one_hour": gaps[2],
            "trip_id_present_in_input": has_trip_id,
            "created_at_is_verified_boarding_time": False,
            "individual_trip_inference_status": "unavailable",
            "reason": (
                "The source has no trip/run identifier, created_at is transaction time, and vehicle labels "
                "are missing for many tickets. Repeated vehicle-route transactions and ticketed stop pairs "
                "do not uniquely identify a single bus trip."
            ),
            "segment_load_status": "unavailable_without_validated_trip_assignment_and_GTFS_stop_sequence",
            "do_not_use_for": ["vehicle occupancy", "empty-seat counts", "live crowd status"],
        }
    finally:
        con.close()
    output = report_path or (PROJECT_ROOT / "outputs" / "trip_inference_assessment.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess whether ETM fields support individual bus-trip inference.")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    print(json.dumps(assess(args.database.resolve(), args.report.resolve() if args.report else None), indent=2, default=str))


if __name__ == "__main__":
    main()


