from __future__ import annotations

import duckdb

from scripts.build_match_candidates import build_candidates


def test_candidate_pipeline_writes_manual_review_outputs(tmp_path):
    database = tmp_path / "matcher-fixture.duckdb"
    con = duckdb.connect(str(database))
    con.execute("CREATE TABLE etm_records(start_stop_name VARCHAR, end_stop_name VARCHAR, route VARCHAR)")
    con.execute("INSERT INTO etm_records VALUES ('A Stop', 'B Stop', '10UP')")
    con.execute("CREATE TABLE gtfs_stops(stop_id VARCHAR, stop_name VARCHAR)")
    con.execute("INSERT INTO gtfs_stops VALUES ('s1', 'A Stop'), ('s2', 'B Stop')")
    con.execute("CREATE TABLE gtfs_routes(route_id VARCHAR, route_short_name VARCHAR, route_long_name VARCHAR)")
    con.execute("INSERT INTO gtfs_routes VALUES ('r1', '10UP', 'Route 10 up')")
    con.close()

    result = build_candidates(database, tmp_path / "review")

    assert result["etm_stop_names"] == 2
    assert result["route_candidate_rows"] == 1
    assert result["auto_accepted_fuzzy_matches"] == 0
    stop_csv = (tmp_path / "review" / "stop_match_candidates.csv").read_text(encoding="utf-8-sig")
    route_csv = (tmp_path / "review" / "route_match_candidates.csv").read_text(encoding="utf-8-sig")
    assert "needs_context_review" in stop_csv
    assert "needs_direction_review" in route_csv


