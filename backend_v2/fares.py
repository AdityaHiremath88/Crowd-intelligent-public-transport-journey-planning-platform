from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import duckdb
from rapidfuzz import fuzz


@dataclass(frozen=True)
class FareStageStop:
    stop_order: int
    stage_number: int | None
    stop_name: str
    is_fare_stage: bool


@lru_cache(maxsize=512)
def _shape_points(path_string: str, mtime_ns: int, size: int, trip_id: str) -> tuple[tuple[float, float], ...]:
    del mtime_ns, size
    con = duckdb.connect(path_string, read_only=True)
    try:
        shape_id = con.execute("SELECT shape_id FROM trips WHERE trip_id = ?", [trip_id]).fetchone()
        if not shape_id or not shape_id[0]:
            return ()
        has_shapes = con.execute("""
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'shapes'
        """).fetchone()[0]
        if not has_shapes:
            return ()
        rows = con.execute("""
            SELECT try_cast(shape_pt_lat AS DOUBLE), try_cast(shape_pt_lon AS DOUBLE)
            FROM shapes WHERE shape_id = ? ORDER BY try_cast(shape_pt_sequence AS INTEGER)
        """, [shape_id[0]]).fetchall()
        return tuple((float(lat), float(lon)) for lat, lon in rows if lat is not None and lon is not None)
    finally:
        con.close()


def _distance_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat_a, lon_a = map(radians, a)
    lat_b, lon_b = map(radians, b)
    delta_lat, delta_lon = lat_b - lat_a, lon_b - lon_a
    haversine = sin(delta_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    return 12_742_000 * asin(min(1.0, sqrt(haversine)))


def _shape_distance_km(
    database_path: Path, trip_id: str, from_stop_id: str, to_stop_id: str,
) -> float | None:
    con = duckdb.connect(str(database_path), read_only=True)
    try:
        stop_rows = con.execute("""
            SELECT stop_id, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE)
            FROM stops WHERE stop_id IN (?, ?)
        """, [from_stop_id, to_stop_id]).fetchall()
        positions = {
            row[0]: (float(row[1]), float(row[2]))
            for row in stop_rows if row[1] is not None and row[2] is not None
        }
        seqs = con.execute("""
            SELECT stop_id, try_cast(stop_sequence AS INTEGER)
            FROM stop_times WHERE trip_id = ? AND stop_id IN (?, ?)
            ORDER BY try_cast(stop_sequence AS INTEGER)
        """, [trip_id, from_stop_id, to_stop_id]).fetchall()
    finally:
        con.close()
    if from_stop_id not in positions or to_stop_id not in positions:
        return None
    starts = [int(seq) for stop_id, seq in seqs if stop_id == from_stop_id and seq is not None]
    ends = [int(seq) for stop_id, seq in seqs if stop_id == to_stop_id and seq is not None]
    if not any(end > start for start in starts for end in ends):
        return None

    stat = database_path.stat()
    points = _shape_points(str(database_path), stat.st_mtime_ns, stat.st_size, trip_id)
    if len(points) < 2:
        return None
    start_hits = [(index, _distance_meters(point, positions[from_stop_id])) for index, point in enumerate(points)]
    end_hits = [(index, _distance_meters(point, positions[to_stop_id])) for index, point in enumerate(points)]
    start_hits = [(index, dist) for index, dist in start_hits if dist <= 1000]
    end_hits = [(index, dist) for index, dist in end_hits if dist <= 1000]
    ordered = [(i, j, d1, d2) for i, d1 in start_hits for j, d2 in end_hits if j > i]
    if not ordered:
        return None
    start, end, start_snap, end_snap = min(ordered, key=lambda hit: (hit[2] + hit[3], hit[1] - hit[0]))
    distance_m = start_snap + end_snap + sum(
        _distance_meters(points[index], points[index + 1]) for index in range(start, end)
    )
    return distance_m / 1000 if distance_m > 0 else None


def normalize_route_key(value: str) -> str:
    value = re.sub(r"\broute\s*(?:no\.?\s*)?", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:dn|dwn)\b", "DOWN", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def normalize_stop_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(terminal|bus stop|fare stage)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)


@lru_cache(maxsize=2048)
def _load_route_stages(path_string: str, mtime_ns: int, size: int, route_key: str) -> tuple[FareStageStop, ...]:
    del mtime_ns, size
    con = duckdb.connect(path_string, read_only=True)
    try:
        table = con.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='main' AND table_name='dtc_fare_stage_stops'
        """).fetchone()
        if not table:
            return ()
        rows = con.execute("""
            SELECT stop_order, fare_stage_number, stop_name, is_fare_stage
            FROM dtc_fare_stage_stops WHERE route_key = ? ORDER BY stop_order
        """, [route_key]).fetchall()
        return tuple(FareStageStop(int(order), number, name, bool(marked)) for order, number, name, marked in rows)
    finally:
        con.close()


def _matched_indices(target_name: str, route_stops: tuple[FareStageStop, ...]) -> tuple[list[int], bool] | None:
    target = normalize_stop_name(target_name)
    if not target:
        return None
    normalized = [normalize_stop_name(row.stop_name) for row in route_stops]
    exact = [index for index, name in enumerate(normalized) if name == target]
    if exact:
        return exact, True

    unique_names = list(dict.fromkeys(normalized))
    if not unique_names:
        return None
    # Fare master and GTFS use inconsistent abbreviations and compound names.
    # Keep close candidates for the ordered-path check below instead of
    # rejecting all non-exact route-stop labels at a high fuzzy threshold.
    scored = sorted(((fuzz.ratio(target, name), name) for name in set(normalized) if name), reverse=True)
    if not scored or scored[0][0] < 65:
        return None
    best_score = scored[0][0]
    candidate_names = {name for score, name in scored if score >= best_score - 8}
    return [index for index, name in enumerate(normalized) if name in candidate_names], False


def _unavailable(note: str) -> dict:
    return {
        "status": "unavailable",
        "currency": "INR",
        "estimated_distance_km": None,
        "fare_stage_intervals": None,
        "ordinary_adult_fare_inr": None,
        "ac_adult_fare_inr": None,
        "confidence": "unavailable",
        "basis": "DTC fare-stage estimate",
        "note": note,
    }


def _ordinary_fare(distance_km: float) -> int:
    if distance_km <= 4:
        return 5
    if distance_km <= 10:
        return 10
    return 15


def _ac_fare(distance_km: float) -> int:
    if distance_km <= 4:
        return 10
    if distance_km <= 8:
        return 15
    if distance_km <= 12:
        return 20
    return 25


def estimate_leg_fare(
    *, route_short_name: str, stop_names: list[str], database_path: Path,
    trip_id: str = "", from_stop_id: str = "", to_stop_id: str = "",
) -> dict:
    """Apply published adult fare bands to GTFS route-shape distance."""
    if len(stop_names) < 2:
        return _unavailable("A complete boarding-to-alighting stop sequence is not available.")
    database_path = database_path.resolve()
    if not database_path.is_file():
        return _unavailable("The local fare-stage database is not available.")

    shape_km = None
    if trip_id and from_stop_id and to_stop_id:
        shape_km = _shape_distance_km(database_path, trip_id, from_stop_id, to_stop_id)
    if shape_km is not None:
        return {
            "status": "estimated", "currency": "INR", "estimated_distance_km": round(shape_km, 2),
            "fare_stage_intervals": None, "ordinary_adult_fare_inr": _ordinary_fare(shape_km),
            "ac_adult_fare_inr": _ac_fare(shape_km), "confidence": "medium",
            "basis": "GTFS route shape distance and published Delhi adult fare bands",
            "note": "Estimated from the scheduled route shape. Actual fare can vary by service and concession.",
        }

    if from_stop_id and to_stop_id:
        con = duckdb.connect(str(database_path), read_only=True)
        try:
            coords = con.execute("""
                SELECT stop_id, try_cast(stop_lat AS DOUBLE), try_cast(stop_lon AS DOUBLE)
                FROM stops WHERE stop_id IN (?, ?)
            """, [from_stop_id, to_stop_id]).fetchall()
        finally:
            con.close()
        coords = {row[0]: (float(row[1]), float(row[2])) for row in coords if row[1] is not None and row[2] is not None}
        if from_stop_id in coords and to_stop_id in coords:
            straight_km = _distance_meters(coords[from_stop_id], coords[to_stop_id]) / 1000
            return {
                "status": "estimated", "currency": "INR", "estimated_distance_km": round(straight_km, 2),
                "fare_stage_intervals": None, "ordinary_adult_fare_inr": _ordinary_fare(straight_km),
                "ac_adult_fare_inr": _ac_fare(straight_km), "confidence": "low",
                "basis": "GTFS stop coordinates and published Delhi adult fare bands",
                "note": "Straight-line fallback; actual bus distance and fare may be higher.",
            }

    stat = database_path.stat()
    route_key = normalize_route_key(route_short_name)
    stages = _load_route_stages(str(database_path), stat.st_mtime_ns, stat.st_size, route_key)
    if not stages:
        return _unavailable("Fare distance could not be derived from route geometry or stop coordinates.")

    start_matches = _matched_indices(stop_names[0], stages)
    end_matches = _matched_indices(stop_names[-1], stages)
    if not start_matches or not end_matches:
        return _unavailable("Fare distance could not be derived from route geometry or stop coordinates.")
    start_indices, start_exact = start_matches
    end_indices, end_exact = end_matches
    path_stop_count = len(stop_names)
    pairs = [(start, end) for start in start_indices for end in end_indices if end > start]
    if not pairs:
        return _unavailable("Fare distance could not be derived from route geometry or stop coordinates.")
    start_index, end_index = min(
        pairs,
        key=lambda pair: (abs((pair[1] - pair[0] + 1) - path_stop_count), pair[1] - pair[0]),
    )

    stage_positions = [
        index for index, row in enumerate(stages)
        if row.is_fare_stage and row.stage_number is not None
    ]
    preceding = [position for position in stage_positions if position <= start_index]
    succeeding = [position for position in stage_positions if position >= end_index]
    if not preceding or not succeeding:
        return _unavailable("The boarding or alighting stop falls outside the mapped fare-stage boundaries.")
    start_boundary = preceding[-1]
    end_boundary = succeeding[0]
    start_stage_order = stage_positions.index(start_boundary)
    end_stage_order = stage_positions.index(end_boundary)
    intervals = max(1, end_stage_order - start_stage_order)
    estimated_km = float(intervals * 2)
    return {
        "status": "estimated",
        "currency": "INR",
        "estimated_distance_km": estimated_km,
        "fare_stage_intervals": intervals,
        "ordinary_adult_fare_inr": _ordinary_fare(estimated_km),
        "ac_adult_fare_inr": _ac_fare(estimated_km),
        "confidence": "low" if not (start_exact and end_exact) else "medium",
        "basis": "DTC route stages, approximately 2 km per stage interval, and published ordinary/AC fare bands",
        "note": "Estimated adult single-ride fare. Actual fare may differ; the selected bus type and concessions are not known.",
    }


def summarize_journey_fares(leg_fares: list[dict]) -> dict:
    estimated = [item for item in leg_fares if item.get("status") == "estimated"]
    if not estimated:
        return {
            "status": "unavailable", "currency": "INR", "estimated_leg_count": 0,
            "total_leg_count": len(leg_fares), "ordinary_adult_total_inr": None,
            "ac_adult_total_inr": None, "estimated_distance_km": None,
            "note": "No leg had a sufficiently matched DTC fare-stage estimate.",
        }
    complete = len(estimated) == len(leg_fares)
    return {
        "status": "estimated" if complete else "partial",
        "currency": "INR",
        "estimated_leg_count": len(estimated),
        "total_leg_count": len(leg_fares),
        "ordinary_adult_total_inr": sum(item["ordinary_adult_fare_inr"] for item in estimated) if complete else None,
        "ac_adult_total_inr": sum(item["ac_adult_fare_inr"] for item in estimated) if complete else None,
        "estimated_distance_km": round(sum(item["estimated_distance_km"] for item in estimated), 1) if complete else None,
        "note": (
            "Estimate sums one fare per bus leg; adult fare bands only. Actual vehicle type, concessions, and exact stage-to-stage tariff are not confirmed."
            if complete else "Only some bus legs could be matched; a journey total is withheld."
        ),
    }
