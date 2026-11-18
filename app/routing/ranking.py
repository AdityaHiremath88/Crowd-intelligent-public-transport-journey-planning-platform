from __future__ import annotations

from dataclasses import replace
from typing import Literal

from app.routing.journey_search import JourneyOption

Preference = Literal["fastest", "balanced", "comfort"]
INITIAL_WEIGHTS: dict[str, dict[str, float]] = {
    "fastest": {"time": 0.80, "crowd": 0.10, "transfers": 0.10},
    "balanced": {"time": 0.50, "crowd": 0.35, "transfers": 0.15},
    "comfort": {"time": 0.20, "crowd": 0.65, "transfers": 0.15},
}


def rank_journeys(
    options: list[JourneyOption],
    preference: Preference,
    max_transfers: int = 1,
    requested_departure_seconds: int | None = None,
) -> list[JourneyOption]:
    """Rank feasible schedules; renormalize over time/transfers while crowd is unavailable."""
    if not options:
        return []
    weights = INITIAL_WEIGHTS[preference]
    available_weight = weights["time"] + weights["transfers"]
    time_weight = weights["time"] / available_weight
    transfer_weight = weights["transfers"] / available_weight
    elapsed_seconds = {
        id(option): option.duration_seconds + max(
            0,
            option.departure_seconds - requested_departure_seconds
            if requested_departure_seconds is not None else 0,
        )
        for option in options
    }
    max_duration = max(elapsed_seconds.values()) or 1
    transfer_scale = max(max_transfers, 1)
    ranked: list[JourneyOption] = []
    for option in options:
        # Include initial wait from the requested departure time. Inter-leg waits
        # are already inside duration_seconds because it spans first departure to arrival.
        time_component = elapsed_seconds[id(option)] / max_duration
        transfer_component = option.transfers / transfer_scale
        score = time_weight * time_component + transfer_weight * transfer_component
        ranked.append(
            replace(
                option,
                score=round(score, 6),
                score_components=(
                    ("time", round(time_component, 6)),
                    ("crowd", None),
                    ("transfers", round(transfer_component, 6)),
                ),
            )
        )
    return sorted(ranked, key=lambda item: (item.score, item.arrival_seconds))


