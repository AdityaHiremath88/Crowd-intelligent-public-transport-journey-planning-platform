from __future__ import annotations

import csv

import duckdb

from scripts.process_etm import process_etm


def write_fixture(path):
    rows = [
        ["passenger_count", "amount", "vehicle_number", "ticket_type_id", "end_stop_name", "route", "start_stop_name", "created_at", "is_ac"],
        ["2", "20", "NULL", "1", " Stop B ", " 8 UP ", "Stop A", "2026-10-01T08:05:00+05:30", "true"],
        ["1", "10", "DL1AA0001", "1", "Stop C", "8UP", "Stop A", "2026-10-01T08:15:00+05:30", "false"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def test_processing_preserves_rows_normalizes_nulls_and_aggregates(tmp_path):
    source = tmp_path / "etm.csv"
    database = tmp_path / "processed.duckdb"
    write_fixture(source)

    result = process_etm(source, database, tmp_path / "quality.json")

    assert result["dataset_rows"] == 2
    assert result["retained_rows"] == 2
    assert result["excluded_rows"] == 0
    assert result["null_vehicle_rows"] == 1
    assert result["distinct_routes"] == 1
    assert len(result["source_sha256"]) == 64
    assert result["source_size_bytes"] == source.stat().st_size
    assert result["schema_version"]
    with duckdb.connect(str(database), read_only=True) as con:
        stop_ids = con.execute("SELECT DISTINCT stop_id FROM stop_demand").fetchall()
        run = con.execute(
            "SELECT input_rows, retained_rows, excluded_rows, run_status FROM pipeline_runs WHERE dataset_name='etm'"
        ).fetchone()
    assert len(stop_ids) == 1
    assert stop_ids[0][0].startswith("etm_")
    assert run == (2, 2, 0, "succeeded")


def test_invalid_etm_schema_rolls_back_previous_processed_tables(tmp_path):
    source = tmp_path / "etm.csv"
    database = tmp_path / "processed.duckdb"
    write_fixture(source)
    process_etm(source, database, tmp_path / "first.json")
    before_hash = duckdb.connect(str(database), read_only=True).execute(
        "SELECT source_sha256 FROM data_quality"
    ).fetchone()[0]
    source.write_text("not,the,required,schema\n1,2,3,4\n", encoding="utf-8")

    try:
        process_etm(source, database, tmp_path / "second.json")
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("Invalid schema should fail processing")

    with duckdb.connect(str(database), read_only=True) as con:
        after_hash = con.execute("SELECT source_sha256 FROM data_quality").fetchone()[0]
        assert con.execute("SELECT count(*) FROM etm_records").fetchone()[0] == 2
    assert after_hash == before_hash

