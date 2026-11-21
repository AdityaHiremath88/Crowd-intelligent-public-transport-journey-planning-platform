from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import duckdb
from rapidfuzz import fuzz


@dataclass(frozen=True)
class FareStageStop:
    stop_order: int
    stage_number: int | None
    stop_name: str
    is_fare_stage: bool


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
    scored = sorted(((fuzz.ratio(target, name), name) for name in unique_names), reverse=True)
    best_score, best_name = scored[0]
    next_score = scored[1][0] if len(scored) > 1 else 0
    if best_score < 92 or best_score - next_score < 5:
        return None
    return [index for index, name in enumerate(normalized) if name == best_name], False


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
) -> dict:
    """Estimate adult fares from matched DTC fare-stage intervals.

    DTC fare stages are treated as approximately 2 km apart. The result is a
    fare-band estimate, not an operator-confirmed fare table lookup.
    """
    if len(stop_names) < 2:
        return _unavailable("A complete boarding-to-alighting stop sequence is not available.")
    database_path = database_path.resolve()
    if not database_path.is_file():
        return _unavailable("The local fare-stage database is not available.")
    stat = database_path.stat()
    route_key = normalize_route_key(route_short_name)
    stages = _load_route_stages(str(database_path), stat.st_mtime_ns, stat.st_size, route_key)
    if not stages:
        return _unavailable("This route direction is not present in the imported DTC fare-stage workbook.")

    start_matches = _matched_indices(stop_names[0], stages)
    end_matches = _matched_indices(stop_names[-1], stages)
    if not start_matches or not end_matches:
        return _unavailable("Boarding or alighting stop could not be matched confidently to this route's fare-stage list.")
    start_indices, start_exact = start_matches
    end_indices, end_exact = end_matches
    path_stop_count = len(stop_names)
    pairs = [(start, end) for start in start_indices for end in end_indices if end > start]
    if not pairs:
        return _unavailable("The route-stage list does not place these stops in the same direction.")
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
