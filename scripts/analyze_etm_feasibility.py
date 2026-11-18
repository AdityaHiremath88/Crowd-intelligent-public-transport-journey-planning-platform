from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.config import DATABASE_PATH, ETM_CSV_PATH, PROJECT_ROOT


def analyze(database_path: Path = DATABASE_PATH, csv_path: Path = ETM_CSV_PATH) -> dict:
    """Describe what the current ETM export supports, without inferring physical loads."""
    if not database_path.is_file():
        raise FileNotFoundError(f"Processed database not found: {database_path}")
    con = duckdb.connect(str(database_path), read_only=True)
    try:
        row = con.execute("""
            SELECT count(*) AS rows,
                   sum(passenger_count)::BIGINT AS passenger_volume,
                   count(DISTINCT (start_stop_name, end_stop_name)) AS distinct_od_label_pairs,
                   count(DISTINCT start_stop_name) AS start_labels,
                   count(DISTINCT end_stop_name) AS end_labels,
                   count(DISTINCT route) AS route_labels,
                   count(*) FILTER (WHERE vehicle_number IS NULL) AS missing_vehicle_rows,
                   count(DISTINCT vehicle_number) AS vehicle_labels,
                   min(transaction_local_time) AS first_transaction,
                   max(transaction_local_time) AS last_transaction,
                   count(DISTINCT transaction_date) AS observed_dates
            FROM etm_records
        """).fetchone()
        top_od = con.execute("""
            SELECT start_stop_name, end_stop_name,
                   sum(passenger_count)::BIGINT passenger_volume,
                   count(*)::BIGINT transaction_count
            FROM etm_records
            GROUP BY 1, 2
            ORDER BY passenger_volume DESC, transaction_count DESC
            LIMIT 25
        """).fetchall()
        top_destinations = con.execute("""
            SELECT end_stop_name, sum(passenger_count)::BIGINT passenger_volume,
                   count(*)::BIGINT transaction_count,
                   count(DISTINCT start_stop_name)::INTEGER distinct_origins
            FROM etm_records GROUP BY 1 ORDER BY passenger_volume DESC LIMIT 25
        """).fetchall()
        missing_by_hour_ac = con.execute("""
            SELECT transaction_hour, is_ac,
                   count(*)::BIGINT transactions,
                   count(*) FILTER (WHERE vehicle_number IS NULL)::BIGINT missing_vehicle,
                   count(*) FILTER (WHERE vehicle_number IS NULL)::DOUBLE / count(*) missing_fraction
            FROM etm_records GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall()
        missing_by_route = con.execute("""
            SELECT route, count(*)::BIGINT transactions,
                   count(*) FILTER (WHERE vehicle_number IS NULL)::BIGINT missing_vehicle,
                   count(*) FILTER (WHERE vehicle_number IS NULL)::DOUBLE / count(*) missing_fraction
            FROM etm_records WHERE route IS NOT NULL GROUP BY 1 HAVING count(*) >= 100
            ORDER BY missing_fraction DESC, transactions DESC LIMIT 25
        """).fetchall()
        ac_profile = con.execute("""
            SELECT is_ac, sum(passenger_count)::BIGINT passenger_volume,
                   count(*)::BIGINT transactions,
                   avg(passenger_count)::DOUBLE avg_passenger_count,
                   count(DISTINCT transaction_date)::INTEGER observed_dates
            FROM etm_records GROUP BY is_ac ORDER BY is_ac
        """).fetchall()
        ticket_profile = con.execute("""
            SELECT ticket_type_id, sum(passenger_count)::BIGINT passenger_volume,
                   count(*)::BIGINT transactions,
                   count(DISTINCT transaction_date)::INTEGER observed_dates
            FROM etm_records GROUP BY ticket_type_id ORDER BY transactions DESC
        """).fetchall()
        stop_role_overlap = con.execute("""
            WITH starts AS (SELECT DISTINCT start_stop_name name FROM etm_records),
                 ends AS (SELECT DISTINCT end_stop_name name FROM etm_records)
            SELECT count(*) FROM starts JOIN ends USING(name)
        """).fetchone()[0]
        start_label_variants = con.execute("""
            WITH normalized AS (
                SELECT start_stop_name label,
                       regexp_replace(lower(trim(start_stop_name)), '[^a-z0-9 ]', '', 'g') canonical
                FROM etm_records WHERE start_stop_name IS NOT NULL
                GROUP BY ALL
            )
            SELECT canonical, count(DISTINCT label)::INTEGER variant_count,
                   list(DISTINCT label ORDER BY label)[:6] examples
            FROM normalized GROUP BY canonical
            HAVING count(DISTINCT label) > 1
            ORDER BY variant_count DESC, canonical LIMIT 25
        """).fetchall()
        route_label_variants = con.execute("""
            WITH normalized AS (
                SELECT route label, regexp_replace(upper(route), '[^A-Z0-9]', '', 'g') canonical
                FROM etm_records WHERE route IS NOT NULL GROUP BY ALL
            )
            SELECT canonical, count(DISTINCT label)::INTEGER variant_count,
                   list(DISTINCT label ORDER BY label)[:6] examples
            FROM normalized GROUP BY canonical
            HAVING count(DISTINCT label) > 1
            ORDER BY variant_count DESC, canonical LIMIT 25
        """).fetchall()
        route_direction_suffixes = con.execute("""
            SELECT count(*) FILTER (WHERE regexp_matches(route, '(UP|DOWN)$')),
                   count(DISTINCT route) FILTER (WHERE regexp_matches(route, '(UP|DOWN)$')),
                   count(DISTINCT regexp_replace(route, '(UP|DOWN)$', ''))
                       FILTER (WHERE regexp_matches(route, '(UP|DOWN)$'))
            FROM etm_records
        """).fetchone()
        source_hash = con.execute(
            "SELECT source_sha256 FROM data_quality WHERE dataset_name='etm' LIMIT 1"
        ).fetchone()
    finally:
        con.close()

    result = {
        "analysis": "ETM evidence feasibility profile",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "source_file": csv_path.name,
            "source_sha256_from_processing": source_hash[0] if source_hash else None,
            "rows": row[0],
            "passenger_count_sum": row[1],
            "unique_ticket_start_end_label_pairs": row[2],
            "unique_start_labels": row[3],
            "unique_end_labels": row[4],
            "unique_route_labels": row[5],
            "missing_vehicle_rows": row[6],
            "missing_vehicle_fraction": row[6] / row[0] if row[0] else None,
            "distinct_non_null_vehicle_labels": row[7],
            "first_transaction_local": str(row[8]),
            "last_transaction_local": str(row[9]),
            "observed_dates": row[10],
            "start_label_end_label_exact_overlap": stop_role_overlap,
        },
        "top_ticket_origin_destination_label_pairs": [
            {"ticket_start_label": item[0], "ticket_destination_label": item[1],
             "passenger_volume": item[2], "transaction_count": item[3]}
            for item in top_od
        ],
        "top_ticket_destinations": [
            {"ticket_destination_label": item[0], "passenger_volume": item[1],
             "transaction_count": item[2], "distinct_ticket_start_labels": item[3]}
            for item in top_destinations
        ],
        "vehicle_missingness_by_transaction_hour_and_source_ac_flag": [
            {"transaction_hour": item[0], "is_ac": item[1], "transactions": item[2],
             "missing_vehicle_rows": item[3], "missing_vehicle_fraction": item[4]}
            for item in missing_by_hour_ac
        ],
        "highest_vehicle_missingness_route_labels_min_100_transactions": [
            {"route_label": item[0], "transactions": item[1],
             "missing_vehicle_rows": item[2], "missing_vehicle_fraction": item[3]}
            for item in missing_by_route
        ],
        "source_ac_field_groups": [
            {"is_ac": item[0], "passenger_volume": item[1], "transactions": item[2],
             "mean_passenger_count_per_row": item[3], "observed_dates": item[4]}
            for item in ac_profile
        ],
        "ticket_type_field_groups": [
            {"ticket_type_id": item[0], "passenger_volume": item[1],
             "transactions": item[2], "observed_dates": item[3]}
            for item in ticket_profile
        ],
        "route_suffix_pattern_diagnostic": {
            "transaction_rows_route_ending_up_or_down": route_direction_suffixes[0],
            "distinct_route_labels_ending_up_or_down": route_direction_suffixes[1],
            "distinct_bases_after_suffix_removal": route_direction_suffixes[2],
            "caveat": "UP/DOWN suffixes are string patterns only; their direction semantics are not validated.",
        },
        "potential_stop_label_normalization_collisions_for_review": [
            {"comparison_key": item[0], "distinct_source_labels": item[1], "examples": item[2]}
            for item in start_label_variants
        ],
        "potential_route_label_normalization_collisions_for_review": [
            {"comparison_key": item[0], "distinct_source_labels": item[1], "examples": item[2]}
            for item in route_label_variants
        ],
        "inference_gates": {
            "ticket_origin_destination_od_label_counts": "supported descriptively; not verified physical board/alight stops",
            "relative_historical_demand": "supported as observed ticket volume within this month, with date coverage",
            "boarding_time_profile": "unsupported; created_at is transaction time, not validated boarding time",
            "passenger_flow_by_trip_segment": "unsupported; no trip assignment or verified alighting event",
            "physical_occupancy_or_capacity_utilization": "unsupported; no passenger-count ground truth or bus-specific capacity",
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile ETM evidence for supported analyses and inference limits.")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--csv", type=Path, default=ETM_CSV_PATH)
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "outputs" / "etm_feasibility.json")
    args = parser.parse_args()
    result = analyze(args.database.resolve(), args.csv.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
