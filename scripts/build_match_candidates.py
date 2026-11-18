from __future__ import annotations

import argparse
import csv
from pathlib import Path

import duckdb

from app.config import DATABASE_PATH, PROJECT_ROOT
from app.data_pipeline.route_matcher import candidate_rows as route_candidate_rows
from app.data_pipeline.stop_matcher import candidate_rows as stop_candidate_rows


def build_candidates(database_path: Path = DATABASE_PATH, output_dir: Path | None = None) -> dict:
    if not database_path.is_file():
        raise FileNotFoundError(f"Processed database not found: {database_path}")
    con = duckdb.connect(str(database_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        missing = {"etm_records", "gtfs_stops", "gtfs_routes"} - tables
        if missing:
            raise ValueError(f"Candidate matching requires ETM and GTFS tables; missing: {', '.join(sorted(missing))}")
        etm_stops = [row[0] for row in con.execute("""
            SELECT DISTINCT start_stop_name FROM etm_records WHERE start_stop_name IS NOT NULL
            UNION SELECT DISTINCT end_stop_name FROM etm_records WHERE end_stop_name IS NOT NULL
            ORDER BY 1
        """).fetchall()]
        gtfs_stops = con.execute("SELECT stop_id, stop_name FROM gtfs_stops ORDER BY stop_id").fetchall()
        etm_routes = [row[0] for row in con.execute(
            "SELECT DISTINCT route FROM etm_records WHERE route IS NOT NULL ORDER BY 1"
        ).fetchall()]
        gtfs_route_rows = con.execute("SELECT * FROM gtfs_routes ORDER BY route_id").fetchall()
        route_columns = [row[0] for row in con.description]
        route_index = {name: index for index, name in enumerate(route_columns)}
        gtfs_routes = [
            (
                row[route_index["route_id"]],
                row[route_index["route_short_name"]] if "route_short_name" in route_index else "",
                row[route_index["route_long_name"]] if "route_long_name" in route_index else "",
            )
            for row in gtfs_route_rows
        ]
    finally:
        con.close()

    stop_rows = stop_candidate_rows(etm_stops, gtfs_stops)
    route_rows = route_candidate_rows(etm_routes, gtfs_routes)
    output_dir = output_dir or (PROJECT_ROOT / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "stop_candidates": output_dir / "stop_match_candidates.csv",
        "route_candidates": output_dir / "route_match_candidates.csv",
    }
    for key, rows in (("stop_candidates", stop_rows), ("route_candidates", route_rows)):
        path = outputs[key]
        fields = list(rows[0]) if rows else (
            ["etm_stop_name", "gtfs_stop_id", "gtfs_stop_name", "match_method", "match_score", "review_status"]
            if key == "stop_candidates" else
            ["etm_route", "gtfs_route_id", "gtfs_route_name", "match_method", "match_score", "review_status"]
        )
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return {
        "etm_stop_names": len(etm_stops),
        "etm_route_labels": len(etm_routes),
        "stop_candidate_rows": len(stop_rows),
        "route_candidate_rows": len(route_rows),
        "outputs": {key: str(value) for key, value in outputs.items()},
        "auto_accepted_fuzzy_matches": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ETM-to-GTFS candidate mappings for manual review.")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build_candidates(args.database.resolve(), args.output_dir.resolve() if args.output_dir else None)
    print(result)


if __name__ == "__main__":
    main()


