from __future__ import annotations

import json
from datetime import UTC, datetime

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend_v2.config import CORS_ORIGINS, DATABASE_PATH

app = FastAPI(
    title="Yuktix Backend v2",
    version="0.2.0",
    description=(
        "Versioned Yuktix bus journey-planning API. Schedule data is static; "
        "historical ticket activity is not physical crowding."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/api/v2/health", tags=["system"])
def health() -> dict:
    """Liveness check; does not require the GTFS database to be present."""
    return {"status": "ok", "service": "yuktix-backend-v2", "generated_at": datetime.now(UTC)}


@app.get("/api/v2/ready", tags=["system"])
def readiness() -> dict:
    """Readiness check for a validated static GTFS import."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail={"code": "GTFS_DATABASE_MISSING", "message": "Run the v2 GTFS import first."},
        )
    con = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        exists = con.execute(
            """SELECT count(*) FROM information_schema.tables
               WHERE table_schema='main' AND table_name='gtfs_import_metadata'"""
        ).fetchone()[0]
        if not exists:
            raise HTTPException(
                status_code=503,
                detail={"code": "GTFS_IMPORT_METADATA_MISSING", "message": "GTFS import metadata is missing."},
            )
        row = con.execute(
            """SELECT imported_at, source_file, source_sha256, usable_for_scheduled_routing,
                      service_start_date, service_end_date, row_counts_json, issues_json
               FROM gtfs_import_metadata ORDER BY imported_at DESC LIMIT 1"""
        ).fetchone()
        if row is None or not row[3]:
            raise HTTPException(
                status_code=503,
                detail={"code": "GTFS_NOT_ROUTABLE", "message": "Imported GTFS failed schedule checks."},
            )
        return {
            "status": "ready",
            "gtfs_available": True,
            "source_file": row[1],
            "source_sha256": row[2],
            "imported_at": row[0],
            "service_start_date": row[4],
            "service_end_date": row[5],
            "row_counts": json.loads(row[6]),
            "issues": json.loads(row[7]),
        }
    finally:
        con.close()
