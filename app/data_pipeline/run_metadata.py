from __future__ import annotations

import uuid


def ensure_pipeline_run_table(con) -> None:
    """Create/upgrade the small append-only ETL run ledger without touching data tables."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id VARCHAR,
            dataset_name VARCHAR,
            source_file VARCHAR,
            source_sha256 VARCHAR,
            source_size_bytes UBIGINT,
            schema_version VARCHAR,
            pipeline_version VARCHAR,
            generated_at TIMESTAMPTZ,
            input_rows UBIGINT,
            retained_rows UBIGINT,
            excluded_rows UBIGINT,
            run_status VARCHAR,
            execution_seconds DOUBLE
        )
    """)
    columns = {row[0] for row in con.execute("DESCRIBE pipeline_runs").fetchall()}
    if "run_id" not in columns:
        con.execute("ALTER TABLE pipeline_runs ADD COLUMN run_id VARCHAR")
    if "execution_seconds" not in columns:
        con.execute("ALTER TABLE pipeline_runs ADD COLUMN execution_seconds DOUBLE")


def new_run_id() -> str:
    return uuid.uuid4().hex
