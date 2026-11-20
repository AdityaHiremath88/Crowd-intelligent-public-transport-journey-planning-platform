from __future__ import annotations

import duckdb

from backend_v2.config import DATABASE_PATH


def connect(*, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if read_only and not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Yuktix v2 database not found: {DATABASE_PATH}")
    if not read_only:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DATABASE_PATH), read_only=read_only)
