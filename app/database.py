from __future__ import annotations

import duckdb
from pathlib import Path

from app.config import DATABASE_PATH


def connect(read_only: bool = True, path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = path or DATABASE_PATH
    if read_only and not path.exists():
        raise FileNotFoundError(f"Processed database not found: {path}")
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def has_tables(*table_names: str) -> bool:
    if not DATABASE_PATH.exists():
        return False
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        available = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        return set(table_names).issubset(available)
    except duckdb.Error:
        return False
    finally:
        con.close()


def gtfs_is_usable(con: duckdb.DuckDBPyConnection | None = None) -> bool:
    """Report schedule usability from the importer quality row, not table presence alone."""
    owns_connection = con is None
    if owns_connection:
        if not DATABASE_PATH.exists():
            return False
        con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        available = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        required = {"gtfs_stops", "gtfs_routes", "gtfs_trips", "gtfs_stop_times", "gtfs_quality"}
        if not required.issubset(available):
            return False
        row = con.execute(
            "SELECT usable_for_scheduled_routing FROM gtfs_quality LIMIT 1"
        ).fetchone()
        return bool(row and str(row[0]).lower() in {"true", "1"})
    except duckdb.Error:
        return False
    finally:
        if owns_connection and con is not None:
            con.close()

