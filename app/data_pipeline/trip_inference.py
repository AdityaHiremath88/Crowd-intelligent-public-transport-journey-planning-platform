from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TripInferenceResult:
    status: str
    trip_id: str | None
    method: str
    confidence: str
    reason: str


def infer_ticket_trip(
    *,
    trip_id: str | None,
    vehicle_number: str | None,
    route_label: str | None,
    transaction_timestamp: str | None,
    timestamp_is_verified_boarding_time: bool,
) -> TripInferenceResult:
    """Only accept a source trip identifier; do not turn vehicle+transaction time into a trip key."""
    if trip_id and trip_id.strip():
        return TripInferenceResult(
            "identified_unvalidated", trip_id.strip(), "source_trip_id", "source_key_present_unvalidated",
            "Trip identity came directly from the source; verify the ID against the GTFS feed before using it.",
        )
    context = [name for name, value in (
        ("vehicle number", vehicle_number), ("route label", route_label),
        ("transaction timestamp", transaction_timestamp),
    ) if value]
    if not timestamp_is_verified_boarding_time:
        reason = "created_at/transaction time is not a verified boarding time; "
    else:
        reason = "No source trip identifier is available; "
    reason += "available context does not uniquely separate repeated runs" + (f" ({', '.join(context)})." if context else ".")
    return TripInferenceResult("unavailable", None, "none", "unavailable", reason)


