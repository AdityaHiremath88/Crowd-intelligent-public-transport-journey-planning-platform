from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from rapidfuzz import fuzz, process


def normalize_route(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


@dataclass(frozen=True)
class RouteCandidate:
    etm_route: str
    gtfs_route_id: str
    gtfs_route_name: str
    match_method: str
    match_score: float
    review_status: str


def candidates_for_route(
    etm_route: str, gtfs_routes: list[tuple[str, str, str]], limit: int = 5
) -> list[RouteCandidate]:
    """Return route ID candidates; fuzzy scores are never treated as an accepted mapping."""
    normalized = {
        route_id: normalize_route(short_name or long_name or route_id)
        for route_id, short_name, long_name in gtfs_routes
    }
    labels = {
        route_id: short_name or long_name or route_id
        for route_id, short_name, long_name in gtfs_routes
    }
    exact = [route_id for route_id, value in normalized.items() if value == normalize_route(etm_route)]
    if len(exact) == 1:
        route_id = exact[0]
        return [RouteCandidate(etm_route, route_id, labels[route_id], "exact_unique", 100.0, "needs_direction_review")]
    if len(exact) > 1:
        return [
            RouteCandidate(etm_route, route_id, labels[route_id], "exact_ambiguous", 100.0, "manual_review")
            for route_id in exact[:limit]
        ]
    scores = process.extract(
        normalize_route(etm_route), list(normalized.values()), scorer=fuzz.WRatio, limit=limit
    )
    return [
        RouteCandidate(etm_route, list(normalized)[index], labels[list(normalized)[index]], "fuzzy_candidate", float(score), "manual_review")
        for _, score, index in scores
    ]


def candidate_rows(etm_routes: list[str], gtfs_routes: list[tuple[str, str, str]]) -> list[dict]:
    return [asdict(candidate) for route in etm_routes for candidate in candidates_for_route(route, gtfs_routes)]



