from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _path_setting(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    return value if value.is_absolute() else PROJECT_ROOT / value


DATABASE_PATH = _path_setting(
    "YUKTIX_V2_DATABASE_PATH", "datasets/processed/yuktix_v2.duckdb"
)
GTFS_ZIP_PATH = _path_setting(
    "YUKTIX_V2_GTFS_ZIP", "datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip"
)
REPORT_PATH = _path_setting(
    "YUKTIX_V2_GTFS_REPORT", "outputs/yuktix_v2_gtfs_import.json"
)
ETM_BUNDLE_PATH = _path_setting(
    "YUKTIX_V2_ETM_BUNDLE", "datasets/shareable/yuktix-october-delhi-clean-data.zip"
)
ETM_IMPORT_REPORT_PATH = _path_setting(
    "YUKTIX_V2_ETM_REPORT", "outputs/yuktix_v2_etm_import.json"
)
FARE_STAGES_PATH = _path_setting(
    "YUKTIX_V2_FARE_STAGES_XLSX", "datasets/shareable/dtc-route-fare-stage-master.xlsx"
)
FARE_STAGE_IMPORT_REPORT_PATH = _path_setting(
    "YUKTIX_V2_FARE_STAGE_REPORT", "outputs/yuktix_v2_fare_stage_import.json"
)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "YUKTIX_V2_CORS_ORIGINS", "http://localhost:5173"
    ).split(",")
    if origin.strip()
]
