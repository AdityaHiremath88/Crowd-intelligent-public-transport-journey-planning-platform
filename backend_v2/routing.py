from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping


def parse_gtfs_time(value: str) -> int:
    """Parse GTFS HH:MM:SS, preserving service times beyond 24:00."""
    try:
        hours_s, minutes_s, seconds_s = value.strip().split(":")
        hours, minutes, seconds = int(hours_s), int(minutes_s), int(seconds_s)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid GTFS time {value!r}; expected HH:MM:SS") from exc
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"Invalid GTFS time {value!r}; minutes and seconds must be 0..59")
    return hours * 3600 + minutes * 60 + seconds


@dataclass(frozen=True)
class StopEvent:
    stop_id: str
    stop_name: str
    stop_sequence: int
    arrival_seconds: int
    departure_seconds: int


@dataclass(frozen=True)
class ScheduledTrip:
    trip_id: str
    route_id: str
    service_id: str
    events: tuple[StopEvent, ...]


@dataclass(frozen=True)
class JourneyLeg:
    trip_id: str
    route_id: str
    from_stop_id: str
    from_stop_name: str
    to_stop_id: str
    to_stop_name: str
    departure_seconds: int
    arrival_seconds: int
    stop_sequence: tuple[str, ...]


@dataclass(frozen=True)
class JourneyOption:
    legs: tuple[JourneyLeg, ...]
    departure_seconds: int
    arrival_seconds: int
    duration_seconds: int
    transfers: int
    transfer_stops: tuple[str, ...]
    score: float
    score_components: dict[str, float | None]


@dataclass(frozen=True)
class SearchIndex:
    boardings_by_stop: Mapping[str, tuple[tuple[int, int, ScheduledTrip, StopEvent], ...]]
    departure_times_by_stop: Mapping[str, tuple[int, ...]]


def build_search_index(trips: Iterable[ScheduledTrip]) -> SearchIndex:
    boardings: dict[str, list[tuple[int, int, ScheduledTrip, StopEvent]]] = {}
    for trip in trips:
        for index, event in enumerate(trip.events[:-1]):
            boardings.setdefault(event.stop_id, []).append((event.departure_seconds, index, trip, event))
    ordered = {key: tuple(sorted(values, key=lambda item: item[0])) for key, values in boardings.items()}
    return SearchIndex(
        ordered,
        {key: tuple(row[0] for row in values) for key, values in ordered.items()},
    )


def active_services_for_date(
    service_date: date,
    calendar_rows: Iterable[Mapping[str, str]],
    exception_rows: Iterable[Mapping[str, str]] = (),
) -> set[str]:
    date_key = service_date.strftime("%Y%m%d")
    weekday = service_date.strftime("%A").lower()
    active = {
        row["service_id"]
        for row in calendar_rows
        if row.get("start_date", "") <= date_key <= row.get("end_date", "")
        and row.get(weekday) == "1"
    }
    for row in exception_rows:
        if row.get("date") == date_key:
            if row.get("exception_type") == "1":
                active.add(row["service_id"])
            elif row.get("exception_type") == "2":
                active.discard(row["service_id"])
    return active


def search_journeys(
    trips: Iterable[ScheduledTrip],
    origin_stop_id: str,
    destination_stop_id: str,
    departure_seconds: int,
    active_service_ids: set[str],
    *,
    max_transfers: int = 1,
    min_transfer_seconds: int = 300,
    limit: int = 10,
    search_index: SearchIndex | None = None,
) -> list[JourneyOption]:
    if origin_stop_id == destination_stop_id:
        return []
    if not 0 <= max_transfers <= 3:
        raise ValueError("max_transfers must be between 0 and 3")
    index = search_index or build_search_index(trips)
    frontier: dict[str, tuple[int, tuple[JourneyLeg, ...]]] = {origin_stop_id: (departure_seconds, ())}
    found: dict[tuple[str, ...], tuple[JourneyLeg, ...]] = {}

    for _ in range(max_transfers + 1):
        next_frontier: dict[str, tuple[int, tuple[JourneyLeg, ...]]] = {}
        for stop_id, (ready_time, previous_legs) in frontier.items():
            earliest = ready_time + (min_transfer_seconds if previous_legs else 0)
            boardings = index.boardings_by_stop.get(stop_id, ())
            start = bisect_left(index.departure_times_by_stop.get(stop_id, ()), earliest)
            for _, start_index, trip, from_event in boardings[start:]:
                if trip.service_id not in active_service_ids or any(leg.trip_id == trip.trip_id for leg in previous_legs):
                    continue
                for end_index in range(start_index + 1, len(trip.events)):
                    to_event = trip.events[end_index]
                    if to_event.arrival_seconds <= from_event.departure_seconds:
                        continue
                    current = next_frontier.get(to_event.stop_id)
                    improves = current is None or to_event.arrival_seconds < current[0]
                    destination = to_event.stop_id == destination_stop_id
                    if not improves and not destination:
                        continue
                    leg = JourneyLeg(
                        trip_id=trip.trip_id,
                        route_id=trip.route_id,
                        from_stop_id=from_event.stop_id,
                        from_stop_name=from_event.stop_name,
                        to_stop_id=to_event.stop_id,
                        to_stop_name=to_event.stop_name,
                        departure_seconds=from_event.departure_seconds,
                        arrival_seconds=to_event.arrival_seconds,
                        stop_sequence=tuple(event.stop_id for event in trip.events[start_index : end_index + 1]),
                    )
                    path = (*previous_legs, leg)
                    if improves:
                        next_frontier[to_event.stop_id] = (to_event.arrival_seconds, path)
                    if destination:
                        found[tuple(item.trip_id for item in path)] = path
        frontier = next_frontier
        if not frontier:
            break

    options = []
    for legs in found.values():
        departure = legs[0].departure_seconds
        arrival = legs[-1].arrival_seconds
        options.append(JourneyOption(
            legs=legs,
            departure_seconds=departure,
            arrival_seconds=arrival,
            duration_seconds=arrival - departure,
            transfers=len(legs) - 1,
            transfer_stops=tuple(leg.to_stop_name for leg in legs[:-1]),
            score=0.0,
            score_components={},
        ))
    return sorted(options, key=lambda item: (item.arrival_seconds, item.transfers, item.departure_seconds))[:limit]


def rank_journeys(
    options: list[JourneyOption], preference: str, *, max_transfers: int, requested_departure_seconds: int,
) -> list[JourneyOption]:
    if not options:
        return []
    ratios = {"fastest": (0.8, 0.2), "balanced": (0.5, 0.5), "comfort": (0.2, 0.8)}
    time_weight, transfer_weight = ratios[preference]
    elapsed = {
        id(option): option.duration_seconds + max(0, option.departure_seconds - requested_departure_seconds)
        for option in options
    }
    scale = max(max(elapsed.values()), 1)
    transfer_scale = max(max_transfers, 1)
    ranked = []
    for option in options:
        time_component = elapsed[id(option)] / scale
        transfer_component = option.transfers / transfer_scale
        score = time_weight * time_component + transfer_weight * transfer_component
        ranked.append(JourneyOption(
            **{**option.__dict__, "score": round(score, 6),
               "score_components": {"time": round(time_component, 6), "crowd": None,
                                   "transfers": round(transfer_component, 6)}}
        ))
    return sorted(ranked, key=lambda item: (item.score, item.arrival_seconds))
