from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

from app.data_pipeline.gtfs_loader import parse_gtfs_time


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
    eta_source: str = "GTFS scheduled times (approximate)"
    crowd_status: str = "unavailable"
    score: float | None = None
    score_components: tuple[tuple[str, float | None], ...] = ()


@dataclass(frozen=True)
class JourneySearchIndex:
    """Immutable boarding index built once when a GTFS schedule is loaded."""

    boardings_by_stop: Mapping[str, tuple[tuple[int, int, ScheduledTrip, StopEvent], ...]]
    departure_times_by_stop: Mapping[str, tuple[int, ...]]
    indexed_trip_count: int
    indexed_stop_event_count: int


def build_journey_search_index(trips: Iterable[ScheduledTrip]) -> JourneySearchIndex:
    """Pre-index departures by stop so request-time searches avoid feed-wide rebuilding."""
    boardings: dict[str, list[tuple[int, int, ScheduledTrip, StopEvent]]] = {}
    trip_count = 0
    event_count = 0
    for trip in trips:
        trip_count += 1
        event_count += len(trip.events)
        for index, event in enumerate(trip.events[:-1]):
            boardings.setdefault(event.stop_id, []).append((event.departure_seconds, index, trip, event))
    ordered: dict[str, tuple[tuple[int, int, ScheduledTrip, StopEvent], ...]] = {}
    departure_times: dict[str, tuple[int, ...]] = {}
    for stop_id, options in boardings.items():
        options.sort(key=lambda item: item[0])
        ordered[stop_id] = tuple(options)
        departure_times[stop_id] = tuple(item[0] for item in options)
    return JourneySearchIndex(ordered, departure_times, trip_count, event_count)


def active_services_for_date(
    service_date: date,
    calendar_rows: Iterable[Mapping[str, str]],
    exception_rows: Iterable[Mapping[str, str]] = (),
) -> set[str]:
    """Resolve GTFS calendar and calendar_dates rules for a service date."""
    date_key = service_date.strftime("%Y%m%d")
    weekday = service_date.strftime("%A").lower()
    active: set[str] = set()
    for row in calendar_rows:
        start = row.get("start_date", "")
        end = row.get("end_date", "")
        if start <= date_key <= end and row.get(weekday) == "1":
            active.add(row["service_id"])
    for row in exception_rows:
        if row.get("date") != date_key:
            continue
        if row.get("exception_type") == "1":
            active.add(row["service_id"])
        elif row.get("exception_type") == "2":
            active.discard(row["service_id"])
    return active


def trip_from_gtfs_rows(
    trip_row: Mapping[str, str], stop_time_rows: Iterable[Mapping[str, str]]
) -> ScheduledTrip:
    events = tuple(
        StopEvent(
            stop_id=row["stop_id"],
            stop_name=row.get("stop_name", row["stop_id"]),
            stop_sequence=int(row["stop_sequence"]),
            arrival_seconds=parse_gtfs_time(row["arrival_time"]),
            departure_seconds=parse_gtfs_time(row["departure_time"]),
        )
        for row in sorted(stop_time_rows, key=lambda item: int(item["stop_sequence"]))
    )
    if len(events) < 2:
        raise ValueError(f"Trip {trip_row.get('trip_id', '<unknown>')} needs at least two stops")
    if any(left.stop_sequence >= right.stop_sequence for left, right in zip(events, events[1:])):
        raise ValueError(f"Trip {trip_row.get('trip_id', '<unknown>')} has non-increasing stop_sequence")
    if any(event.arrival_seconds > event.departure_seconds for event in events):
        raise ValueError(f"Trip {trip_row.get('trip_id', '<unknown>')} departs before it arrives at a stop")
    if any(left.departure_seconds > right.arrival_seconds for left, right in zip(events, events[1:])):
        raise ValueError(f"Trip {trip_row.get('trip_id', '<unknown>')} has decreasing scheduled times")
    return ScheduledTrip(
        trip_id=trip_row["trip_id"],
        route_id=trip_row["route_id"],
        service_id=trip_row["service_id"],
        events=events,
    )


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
    search_index: JourneySearchIndex | None = None,
) -> list[JourneyOption]:
    """Find earliest-arrival journeys across bounded boarding rounds."""
    if origin_stop_id == destination_stop_id:
        return []
    if max_transfers < 0 or max_transfers > 3:
        raise ValueError("This routing version supports at most three transfers")
    if departure_seconds < 0 or min_transfer_seconds < 0 or limit < 1:
        raise ValueError("Departure, transfer and limit values must be non-negative (limit >= 1)")

    index = search_index or build_journey_search_index(trips)

    # The earliest label at a stop dominates later labels for the same boarding
    # round when crowd data is unavailable. Each round adds one vehicle boarding.
    frontier: dict[str, tuple[int, tuple[JourneyLeg, ...]]] = {origin_stop_id: (departure_seconds, ())}
    options: dict[tuple[str, ...], JourneyOption] = {}
    for _boarding_round in range(1, max_transfers + 2):
        next_frontier: dict[str, tuple[int, tuple[JourneyLeg, ...]]] = {}
        for stop_id, (ready_time, previous_legs) in frontier.items():
            transfer_buffer = min_transfer_seconds if previous_legs else 0
            earliest_board_time = ready_time + transfer_buffer
            boardings = index.boardings_by_stop.get(stop_id, ())
            first_index = bisect_left(index.departure_times_by_stop.get(stop_id, ()), earliest_board_time)
            for boarding_position in range(first_index, len(boardings)):
                _, start_index, trip, from_event = boardings[boarding_position]
                if trip.service_id not in active_service_ids:
                    continue
                if any(leg.trip_id == trip.trip_id for leg in previous_legs):
                    continue
                for to_index in range(start_index + 1, len(trip.events)):
                    to_event = trip.events[to_index]
                    if to_event.arrival_seconds <= from_event.departure_seconds:
                        continue
                    current = next_frontier.get(to_event.stop_id)
                    improves_frontier = current is None or to_event.arrival_seconds < current[0]
                    is_destination = to_event.stop_id == destination_stop_id
                    if not improves_frontier and not is_destination:
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
                        stop_sequence=tuple(event.stop_id for event in trip.events[start_index : to_index + 1]),
                    )
                    path = (*previous_legs, leg)
                    if improves_frontier:
                        next_frontier[to_event.stop_id] = (to_event.arrival_seconds, path)
                    if is_destination:
                        route_key = tuple(item.trip_id for item in path)
                        scheduled_start = path[0].departure_seconds
                        key = (*route_key, str(scheduled_start), str(to_event.arrival_seconds))
                        options[key] = JourneyOption(
                            legs=path,
                            departure_seconds=scheduled_start,
                            arrival_seconds=to_event.arrival_seconds,
                            duration_seconds=to_event.arrival_seconds - scheduled_start,
                            transfers=len(path) - 1,
                            transfer_stops=tuple(item.to_stop_name for item in path[:-1]),
                        )
        frontier = next_frontier
        if not frontier:
            break

    return sorted(
        options.values(),
        key=lambda journey: (journey.arrival_seconds, journey.transfers, journey.departure_seconds),
    )[:limit]



