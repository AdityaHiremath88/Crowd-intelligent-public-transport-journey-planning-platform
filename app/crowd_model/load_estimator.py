from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TicketJourney:
    trip_id: str | None
    board_sequence: int
    alight_sequence: int
    passenger_count: int
    transaction_id: str | None = None


@dataclass(frozen=True)
class SegmentLoad:
    from_stop_id: str
    to_stop_id: str
    ticketed_passenger_load: int
    contributing_transactions: int
    basis: str = "ticketed_journey_covering_segment"
    occupancy_status: str = "not_ground_truth"


@dataclass(frozen=True)
class SegmentLoadResult:
    status: str
    trip_id: str | None
    segments: tuple[SegmentLoad, ...]
    reason: str | None


def estimate_segment_load(
    stop_sequence: list[tuple[int, str]],
    journeys: list[TicketJourney],
    *,
    expected_trip_id: str | None,
) -> SegmentLoadResult:
    """Sum ticketed journeys across segments only when a validated trip key is supplied."""
    if expected_trip_id is None:
        return SegmentLoadResult(
            "unavailable", None, (),
            "A validated individual trip ID is required; vehicle and transaction time alone are insufficient.",
        )
    ordered = sorted(stop_sequence)
    if len(ordered) < 2 or len({sequence for sequence, _ in ordered}) != len(ordered):
        return SegmentLoadResult("invalid_input", expected_trip_id, (), "Stop sequence must contain unique ordered stops.")
    if any(left[0] >= right[0] for left, right in zip(ordered, ordered[1:])):
        return SegmentLoadResult("invalid_input", expected_trip_id, (), "Stop sequence is not strictly increasing.")

    trip_stop_sequences = {sequence for sequence, _ in ordered}
    matching_journeys = [journey for journey in journeys if journey.trip_id == expected_trip_id]
    if any(
        journey.passenger_count <= 0
        or journey.board_sequence >= journey.alight_sequence
        or journey.board_sequence not in trip_stop_sequences
        or journey.alight_sequence not in trip_stop_sequences
        for journey in matching_journeys
    ):
        return SegmentLoadResult(
            "invalid_input", expected_trip_id, (),
            "Trip-matched ticket journeys must have positive passenger counts and valid increasing stop sequences.",
        )
    transaction_ids = [journey.transaction_id for journey in matching_journeys if journey.transaction_id]
    if len(transaction_ids) != len(set(transaction_ids)):
        return SegmentLoadResult(
            "invalid_input", expected_trip_id, (),
            "Duplicate transaction IDs were supplied for this trip; resolve duplicates before summing.",
        )

    loads: list[SegmentLoad] = []
    for index, (from_sequence, from_stop) in enumerate(ordered[:-1]):
        to_sequence, to_stop = ordered[index + 1]
        passengers = 0
        transactions = 0
        for journey in journeys:
            if journey.trip_id != expected_trip_id:
                continue
            # A journey covers the whole adjacent segment only when its boarding
            # sequence is no later than the segment start and its alighting
            # sequence is no earlier than the segment end.
            if journey.board_sequence <= from_sequence and journey.alight_sequence >= to_sequence:
                passengers += journey.passenger_count
                transactions += 1
        loads.append(SegmentLoad(from_stop, to_stop, passengers, transactions))
    if not any(segment.contributing_transactions for segment in loads):
        return SegmentLoadResult("unavailable", expected_trip_id, tuple(loads), "No validated ticket journeys cover this trip's segments.")
    return SegmentLoadResult("ticketed_load_proxy", expected_trip_id, tuple(loads), None)


