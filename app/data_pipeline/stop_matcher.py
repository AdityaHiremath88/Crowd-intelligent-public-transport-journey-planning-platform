from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from rapidfuzz import fuzz, process


def normalize_stop_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip().casefold())
    return re.sub(r"[^\w ]", "", value)


@dataclass(frozen=True)
class StopMatchCandidate:
    etm_stop_name: str
    gtfs_stop_id: str
    gtfs_stop_name: str
    match_method: str
    match_score: float
    review_status: str


def candidates_for_stop(etm_name: str, gtfs_stops: list[tuple[str, str]], limit: int = 5) -> list[StopMatchCandidate]:
    """Suggest candidates for review. Fuzzy results are never accepted automatically."""
    normalized = {stop_id: normalize_stop_name(name) for stop_id, name in gtfs_stops}
    name_by_id = {stop_id: name for stop_id, name in gtfs_stops}
    exact = [stop_id for stop_id, key in normalized.items() if key == normalize_stop_name(etm_name)]
    if len(exact) == 1:
        stop_id = exact[0]
        return [StopMatchCandidate(etm_name, stop_id, name_by_id[stop_id], "exact_unique", 100.0, "needs_context_review")]
    if len(exact) > 1:
        return [
            StopMatchCandidate(etm_name, stop_id, name_by_id[stop_id], "exact_ambiguous", 100.0, "manual_review")
            for stop_id in exact[:limit]
        ]

    choices = [normalize_stop_name(name) for _, name in gtfs_stops]
    fuzzy = process.extract(
        normalize_stop_name(etm_name),
        choices,
        scorer=fuzz.WRatio,
        limit=limit,
    )
    return [
        StopMatchCandidate(etm_name, gtfs_stops[index][0], gtfs_stops[index][1], "fuzzy_candidate", float(score), "manual_review")
        for _, score, index in fuzzy
    ]


def candidate_rows(etm_names: list[str], gtfs_stops: list[tuple[str, str]]) -> list[dict]:
    return [asdict(candidate) for name in etm_names for candidate in candidates_for_stop(name, gtfs_stops)]



