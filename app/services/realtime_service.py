from __future__ import annotations

import asyncio
import logging
import math
import sqlite3
import time
from contextlib import contextmanager
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from app.config import (
    COMMUNITY_DB_PATH, GTFS_RT_API_KEY, GTFS_RT_AUTH_HEADER,
    GTFS_RT_AUTH_MODE, GTFS_RT_KEY_PARAMETER, GTFS_RT_MAX_STALENESS_SECONDS,
    GTFS_RT_POLL_SECONDS, GTFS_RT_TIMEOUT_SECONDS, GTFS_RT_URL,
)

logger = logging.getLogger(__name__)
MAX_FEED_BYTES = 10 * 1024 * 1024
MAX_FUTURE_SKEW_SECONDS = 60
DATA_SOURCE = "authorized GTFS-Realtime VehiclePositions feed"


class RealtimeFeedError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RealtimeStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or COMMUNITY_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS realtime_vehicles (
                    vehicle_id TEXT PRIMARY KEY, trip_id TEXT, route_id TEXT,
                    latitude REAL NOT NULL, longitude REAL NOT NULL,
                    bearing REAL, speed_mps REAL, current_stop_id TEXT,
                    current_stop_sequence INTEGER, current_status TEXT,
                    position_timestamp INTEGER NOT NULL, feed_timestamp INTEGER,
                    received_at INTEGER NOT NULL, route_id_matched INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS realtime_status (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    last_attempt_at INTEGER, last_success_at INTEGER, feed_timestamp INTEGER,
                    last_error_code TEXT, malformed_count INTEGER NOT NULL DEFAULT 0,
                    stale_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO realtime_status(singleton) VALUES(1);
            """)
            columns = {row[1] for row in con.execute("PRAGMA table_info(realtime_vehicles)").fetchall()}
            if "route_id_matched" not in columns:
                con.execute("ALTER TABLE realtime_vehicles ADD COLUMN route_id_matched INTEGER NOT NULL DEFAULT 0")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con

    @contextmanager
    def _session(self):
        con = self._connect()
        try:
            with con:
                yield con
        finally:
            con.close()

    def mark_attempt(self, at: int) -> None:
        with self._session() as con:
            con.execute("UPDATE realtime_status SET last_attempt_at=? WHERE singleton=1", (at,))

    def mark_error(self, at: int, code: str) -> None:
        with self._session() as con:
            con.execute("UPDATE realtime_status SET last_attempt_at=?,last_error_code=? WHERE singleton=1", (at, code))

    def replace_snapshot(
        self, vehicles: list[dict], *, attempted_at: int, completed_at: int, feed_timestamp: int,
        stale_count: int, malformed_count: int, duplicate_count: int,
    ) -> None:
        with self._session() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM realtime_vehicles")
            con.executemany(
                """INSERT INTO realtime_vehicles(
                    vehicle_id,trip_id,route_id,latitude,longitude,bearing,speed_mps,current_stop_id,
                    current_stop_sequence,current_status,position_timestamp,feed_timestamp,received_at,route_id_matched
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(
                    v["vehicle_id"], v["trip_id"], v["route_id"], v["latitude"], v["longitude"],
                    v["bearing"], v["speed_meters_per_second"], v["current_stop_id"],
                    v["current_stop_sequence"], v["current_status"], v["position_timestamp"],
                    v["feed_timestamp"], completed_at,
                    int(v.get("route_id_matched", False)),
                ) for v in vehicles],
            )
            con.execute(
                """UPDATE realtime_status SET last_attempt_at=?,last_success_at=?,feed_timestamp=?,
                   last_error_code=NULL,malformed_count=?,stale_count=?,duplicate_count=? WHERE singleton=1""",
                (attempted_at, completed_at, feed_timestamp, malformed_count, stale_count, duplicate_count),
            )

    def status(self) -> dict:
        with self._session() as con:
            row = con.execute("SELECT * FROM realtime_status WHERE singleton=1").fetchone()
            current = con.execute("SELECT count(*) FROM realtime_vehicles").fetchone()[0]
            return {**dict(row), "current_vehicle_count": current} if row else {"current_vehicle_count": 0}

    def vehicles(self, *, route_id: str | None = None) -> list[dict]:
        with self._session() as con:
            sql = "SELECT * FROM realtime_vehicles"
            args: tuple = ()
            if route_id is not None:
                sql += " WHERE route_id=?"
                args = (route_id,)
            return [dict(row) for row in con.execute(sql + " ORDER BY vehicle_id", args).fetchall()]


store = RealtimeStore()


def _epoch(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def parse_vehicle_positions(
    payload: bytes,
    *,
    routes: set[str] | None = None,
    trips: dict[str, str] | None = None,
    stops: set[str] | None = None,
    now_epoch: int | None = None,
    max_age_seconds: int = GTFS_RT_MAX_STALENESS_SECONDS,
) -> dict:
    if not payload or len(payload) > MAX_FEED_BYTES:
        raise RealtimeFeedError("FEED_SIZE_INVALID")
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(payload)
    except DecodeError as exc:
        raise RealtimeFeedError("PROTOBUF_INVALID") from exc
    if not feed.HasField("header") or not feed.header.gtfs_realtime_version:
        raise RealtimeFeedError("FEED_HEADER_INVALID")
    if feed.header.HasField("incrementality") and feed.header.incrementality != gtfs_realtime_pb2.FeedHeader.FULL_DATASET:
        raise RealtimeFeedError("DIFFERENTIAL_FEED_UNSUPPORTED")
    now_epoch = int(time.time()) if now_epoch is None else now_epoch
    routes, trips, stops = routes or set(), trips or {}, stops or set()
    feed_timestamp = int(feed.header.timestamp) if feed.header.HasField("timestamp") else None
    if feed_timestamp is not None and feed_timestamp > now_epoch + MAX_FUTURE_SKEW_SECONDS:
        raise RealtimeFeedError("FEED_TIMESTAMP_IN_FUTURE")
    if feed_timestamp is not None and now_epoch - feed_timestamp > max_age_seconds:
        raise RealtimeFeedError("FEED_STALE")
    if not feed.entity:
        raise RealtimeFeedError("FEED_EMPTY")

    best_by_vehicle: dict[str, dict] = {}
    malformed = stale = duplicates = 0
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle
        try:
            if not vehicle.HasField("position"):
                raise ValueError("position missing")
            vehicle_id = vehicle.vehicle.id.strip() if vehicle.HasField("vehicle") and vehicle.vehicle.id else ""
            if not vehicle_id or len(vehicle_id) > 128:
                raise ValueError("vehicle id invalid")
            lat, lon = float(vehicle.position.latitude), float(vehicle.position.longitude)
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("coordinates invalid")
            timestamp = int(vehicle.timestamp) if vehicle.HasField("timestamp") else feed_timestamp
            if timestamp is None or timestamp > now_epoch + MAX_FUTURE_SKEW_SECONDS:
                raise ValueError("timestamp invalid")
            if now_epoch - timestamp > max_age_seconds:
                stale += 1
                continue
            trip_id = vehicle.trip.trip_id.strip() if vehicle.HasField("trip") and vehicle.trip.trip_id else None
            route_id = vehicle.trip.route_id.strip() if vehicle.HasField("trip") and vehicle.trip.route_id else None
            route_id_matched = False
            if trip_id and trips:
                if trip_id not in trips:
                    raise ValueError("trip is not in static GTFS")
                mapped_route = trips[trip_id]
                if route_id and route_id != mapped_route:
                    raise ValueError("trip and route disagree")
                route_id = mapped_route
                route_id_matched = True
            if route_id and routes and route_id not in routes:
                raise ValueError("route is not in static GTFS")
            if route_id and routes and route_id in routes:
                route_id_matched = True
            stop_id = vehicle.stop_id if vehicle.HasField("stop_id") and vehicle.stop_id else None
            if stop_id and stops and stop_id not in stops:
                raise ValueError("stop is not in static GTFS")
            current_status = None
            if vehicle.HasField("current_status"):
                current_status = gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status)
            item = {
                "vehicle_id": vehicle_id, "trip_id": trip_id, "route_id": route_id,
                "route_id_matched": route_id_matched,
                "latitude": lat, "longitude": lon,
                "bearing": float(vehicle.position.bearing) if vehicle.position.HasField("bearing") else None,
                "speed_meters_per_second": float(vehicle.position.speed) if vehicle.position.HasField("speed") else None,
                "current_stop_id": stop_id,
                "current_stop_sequence": int(vehicle.current_stop_sequence) if vehicle.HasField("current_stop_sequence") else None,
                "current_status": current_status, "position_timestamp": timestamp,
                "feed_timestamp": feed_timestamp,
            }
            if vehicle_id in best_by_vehicle:
                duplicates += 1
            if vehicle_id not in best_by_vehicle or timestamp > best_by_vehicle[vehicle_id]["position_timestamp"]:
                best_by_vehicle[vehicle_id] = item
        except (ValueError, TypeError, OverflowError):
            malformed += 1
    if not best_by_vehicle:
        raise RealtimeFeedError("FEED_EMPTY")
    return {
        "vehicles": list(best_by_vehicle.values()), "feed_timestamp": feed_timestamp,
        "malformed_count": malformed, "stale_count": stale, "duplicate_count": duplicates,
    }


def _build_request() -> urllib.request.Request:
    if not GTFS_RT_URL:
        raise RealtimeFeedError("FEED_NOT_CONFIGURED")
    if GTFS_RT_AUTH_MODE not in {"header", "query"}:
        raise RealtimeFeedError("AUTH_MODE_INVALID")
    url = GTFS_RT_URL
    parsed_url = urllib.parse.urlsplit(url)
    loopback_http = parsed_url.scheme == "http" and parsed_url.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed_url.scheme != "https" and not loopback_http:
        raise RealtimeFeedError("HTTPS_REQUIRED")
    if not GTFS_RT_API_KEY:
        raise RealtimeFeedError("CREDENTIAL_MISSING")
    # Transport Stack's feed endpoint returns 406 when an Accept header is sent.
    headers = {}
    if GTFS_RT_API_KEY:
        if GTFS_RT_AUTH_MODE == "header":
            headers[GTFS_RT_AUTH_HEADER] = f"Bearer {GTFS_RT_API_KEY}" if GTFS_RT_AUTH_HEADER.lower() == "authorization" else GTFS_RT_API_KEY
        else:
            parsed = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            query.append((GTFS_RT_KEY_PARAMETER, GTFS_RT_API_KEY))
            url = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))
    elif GTFS_RT_AUTH_MODE == "query":
        raise RealtimeFeedError("CREDENTIAL_MISSING")
    return urllib.request.Request(url, headers=headers, method="GET")


def _static_gtfs_ids() -> tuple[set[str], dict[str, str], set[str]]:
    """Load validated GTFS identifiers for exact feed matching; raw IDs remain available if absent."""
    con = None
    try:
        from app.database import connect, gtfs_is_usable

        con = connect()
        if not gtfs_is_usable(con):
            return set(), {}, set()
        routes = {str(row[0]) for row in con.execute("SELECT route_id FROM gtfs_routes").fetchall()}
        trips = {
            str(trip_id): str(route_id)
            for trip_id, route_id in con.execute("SELECT trip_id, route_id FROM gtfs_trips").fetchall()
        }
        stops = {str(row[0]) for row in con.execute("SELECT stop_id FROM gtfs_stops").fetchall()}
        return routes, trips, stops
    except Exception as exc:
        # Static GTFS is optional; in its absence, show provider IDs without claiming a match.
        logger.info("GTFS-RT static ID matching unavailable error_type=%s", type(exc).__name__)
        return set(), {}, set()
    finally:
        if con is not None:
            con.close()


def poll_once(*, now_epoch: int | None = None) -> dict:
    attempt = int(time.time()) if now_epoch is None else now_epoch
    store.mark_attempt(attempt)
    try:
        request = _build_request()
        opener = urllib.request.build_opener(_NoRedirectHandler)
        with opener.open(request, timeout=GTFS_RT_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_FEED_BYTES + 1)
        routes, trips, stops = _static_gtfs_ids()
        parsed = parse_vehicle_positions(
            payload, routes=routes, trips=trips, stops=stops, now_epoch=attempt
        )
        feed_timestamp = parsed["feed_timestamp"] if parsed["feed_timestamp"] is not None else attempt
        completed = int(time.time()) if now_epoch is None else now_epoch
        store.replace_snapshot(
            parsed["vehicles"], attempted_at=attempt, completed_at=completed, feed_timestamp=feed_timestamp,
            stale_count=parsed["stale_count"], malformed_count=parsed["malformed_count"],
            duplicate_count=parsed["duplicate_count"],
        )
        return {"status": "healthy", **parsed}
    except urllib.error.HTTPError as exc:
        code = "AUTHORIZATION_FAILED" if exc.code in {401, 403} else f"HTTP_{exc.code}"
    except urllib.error.URLError as exc:
        code = "NETWORK_ERROR" if not isinstance(exc.reason, TimeoutError) else "TIMEOUT"
    except TimeoutError:
        code = "TIMEOUT"
    except RealtimeFeedError as exc:
        code = exc.code
    except Exception:
        logger.error("GTFS-RT poll failed code=INTERNAL_POLL_ERROR")
        code = "INTERNAL_POLL_ERROR"
    try:
        store.mark_error(attempt, code)
    except sqlite3.Error:
        logger.exception("GTFS-RT status persistence failed")
    logger.warning("GTFS-RT poll failed code=%s", code)
    return {"status": "error", "error_code": code}


async def polling_loop() -> None:
    delay = GTFS_RT_POLL_SECONDS
    while True:
        result = await asyncio.to_thread(poll_once)
        if result.get("status") == "healthy":
            delay = GTFS_RT_POLL_SECONDS
        else:
            delay = min(max(2, delay * 2), 300)
        await asyncio.sleep(delay)


def current_snapshot() -> tuple[dict, list[dict]]:
    status = store.status()
    now = int(time.time())
    last_success = status.get("last_success_at")
    age = now - int(last_success) if last_success is not None else None
    max_age = GTFS_RT_MAX_STALENESS_SECONDS
    configured = bool(GTFS_RT_URL and GTFS_RT_API_KEY)
    authorized = (
        configured
        and status.get("last_success_at") is not None
        and status.get("last_error_code") not in {"AUTHORIZATION_FAILED", "HTTP_401", "HTTP_403"}
    )
    if not configured:
        state = "NOT_CONFIGURED"
    elif status.get("last_error_code"):
        state = "ERROR"
    elif age is None or age > max_age:
        state = "STALE" if age is not None else "UNAVAILABLE"
    else:
        state = "HEALTHY"
    # Preserve last-known positions across failed polls and expose their observation age.
    vehicles = store.vehicles() if status.get("last_success_at") is not None else []
    stale_count = status.get("stale_count", 0)
    if state == "STALE":
        stale_count = max(stale_count, status.get("current_vehicle_count", 0))
    return ({**status, "status": state, "configured": configured, "authorized": authorized,
             "stale_vehicle_count": stale_count}, vehicles)


