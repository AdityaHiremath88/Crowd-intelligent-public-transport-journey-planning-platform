from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _int_setting(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def project_path(env_name: str, default: str) -> Path:
    value = Path(os.getenv(env_name, default))
    return value if value.is_absolute() else PROJECT_ROOT / value


DATABASE_PATH = project_path("CROWDWISE_DATABASE_PATH", "datasets/processed/crowdwise.duckdb")
ETM_CSV_PATH = project_path("CROWDWISE_ETM_CSV", "datasets/etm/raw/October-Delhi.csv")
GTFS_ZIP_PATH = project_path("CROWDWISE_GTFS_ZIP", "datasets/gtfs/raw/delhi_buses_static_gtfs_v1.zip")
COMMUNITY_DB_PATH = project_path("CROWDWISE_COMMUNITY_DB_PATH", "datasets/community/crowdwise_signals.sqlite3")
GTFS_RT_URL = os.getenv(
    "DELHI_GTFS_RT_URL",
    os.getenv(
        "CROWDWISE_GTFS_RT_URL",
        "https://delhi.transportstack.in/api/dataset/otd/get-file?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb",
    ),
).strip()
GTFS_RT_API_KEY = os.getenv(
    "DELHI_GTFS_RT_API_KEY",
    os.getenv("DELHI_BUS_API_KEY", os.getenv("CROWDWISE_GTFS_RT_API_KEY", "")),
).strip()
GTFS_RT_AUTH_MODE = os.getenv("CROWDWISE_GTFS_RT_AUTH_MODE", "header").strip().lower()
GTFS_RT_AUTH_HEADER = os.getenv("CROWDWISE_GTFS_RT_AUTH_HEADER", "x-api-key").strip()
GTFS_RT_KEY_PARAMETER = os.getenv("CROWDWISE_GTFS_RT_KEY_PARAMETER", "key").strip()
GTFS_RT_POLL_SECONDS = _int_setting("CROWDWISE_GTFS_RT_POLL_SECONDS", 60, 30)
GTFS_RT_TIMEOUT_SECONDS = _int_setting("CROWDWISE_GTFS_RT_TIMEOUT_SECONDS", 8, 1)
GTFS_RT_MAX_STALENESS_SECONDS = _int_setting("CROWDWISE_GTFS_RT_MAX_STALENESS_SECONDS", 180, 30)
REPORT_HMAC_SECRET = os.getenv("CROWDWISE_REPORT_HMAC_SECRET", "")
COMMUNITY_REPORT_TTL_SECONDS = _int_setting("CROWDWISE_REPORT_TTL_SECONDS", 1200, 60)
PRESENCE_TTL_SECONDS = _int_setting("CROWDWISE_PRESENCE_TTL_SECONDS", 600, 60)
COMMUNITY_RATE_LIMIT_PER_HOUR = _int_setting("CROWDWISE_COMMUNITY_RATE_LIMIT_PER_HOUR", 10, 1)
COMMUNITY_NETWORK_RATE_LIMIT_PER_HOUR = _int_setting("CROWDWISE_COMMUNITY_NETWORK_RATE_LIMIT_PER_HOUR", 100, 1)
CROWDWISE_GEOFENCE_RADIUS_METERS = _int_setting("CROWDWISE_GEOFENCE_RADIUS_METERS", 100, 25)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CROWDWISE_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

