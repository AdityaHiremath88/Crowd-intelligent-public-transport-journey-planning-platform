from __future__ import annotations

from app.crowd_model.classifier import classify_capacity_load, classify_relative_load
from app.crowd_model.confidence import ConfidenceEvidence, assess_confidence
from app.crowd_model.load_estimator import TicketJourney, estimate_segment_load
from app.data_pipeline.trip_inference import infer_ticket_trip


def test_segment_load_sums_ticketed_journeys_by_stop_sequence():
    result = estimate_segment_load(
        [(1, "A"), (2, "B"), (3, "C"), (4, "D")],
        [
            TicketJourney("trip-1", 1, 3, 10),
            TicketJourney("trip-1", 2, 4, 8),
            TicketJourney("trip-1", 3, 4, 5),
            TicketJourney("another-trip", 1, 4, 100),
        ],
        expected_trip_id="trip-1",
    )
    assert result.status == "ticketed_load_proxy"
    assert [segment.ticketed_passenger_load for segment in result.segments] == [10, 18, 13]
    assert all(segment.occupancy_status == "not_ground_truth" for segment in result.segments)


def test_segment_load_refuses_to_infer_missing_trip_identity():
    result = estimate_segment_load(
        [(1, "A"), (2, "B")], [TicketJourney(None, 1, 2, 1)], expected_trip_id=None
    )
    assert result.status == "unavailable"
    assert result.segments == ()


def test_segment_load_does_not_count_ticket_alighting_before_segment_end():
    result = estimate_segment_load(
        [(1, "A"), (3, "C")],
        [TicketJourney("trip-1", 1, 2, 3)],
        expected_trip_id="trip-1",
    )
    assert result.status == "invalid_input"
    assert result.segments == ()


def test_segment_load_rejects_duplicate_transaction_ids():
    result = estimate_segment_load(
        [(1, "A"), (2, "B")],
        [TicketJourney("trip-1", 1, 2, 2, "tx1"), TicketJourney("trip-1", 1, 2, 2, "tx1")],
        expected_trip_id="trip-1",
    )
    assert result.status == "invalid_input"
    assert "Duplicate transaction IDs" in result.reason


def test_crowd_classification_requires_capacity_or_calibrated_relative_bands():
    assert classify_capacity_load(40, None).status == "unavailable"
    assert classify_capacity_load(40, 100).status == "unavailable"
    assert classify_capacity_load(40, 100, comfortable_max_fraction=0.5, moderate_max_fraction=0.75, crowded_max_fraction=1.0).category == "Comfortable"
    assert classify_capacity_load(60, 100, comfortable_max_fraction=0.5, moderate_max_fraction=0.75, crowded_max_fraction=1.0).category == "Moderate"
    assert classify_capacity_load(90, 100, comfortable_max_fraction=0.5, moderate_max_fraction=0.75, crowded_max_fraction=1.0).category == "Crowded"
    assert classify_capacity_load(101, 100, comfortable_max_fraction=0.5, moderate_max_fraction=0.75, crowded_max_fraction=1.0).category == "Very crowded"
    assert classify_relative_load(9, comfortable_max=5, moderate_max=8, crowded_max=12, calibration_days=6).status == "unavailable"
    assert classify_relative_load(9, comfortable_max=5, moderate_max=8, crowded_max=12, calibration_days=14).category == "Crowded"


def test_confidence_is_unavailable_without_matching_and_trip_evidence():
    missing = ConfidenceEvidence(10, 0.9, None, None, None, None, 2)
    assert assess_confidence(missing).status == "unavailable"
    evidence = ConfidenceEvidence(10, 0.9, 0.95, 0.9, 0.8, 0.85, 2)
    result = assess_confidence(evidence)
    assert result.status == "assessed"
    assert result.level == "high"
    assert result.score is not None


def test_vehicle_route_transaction_context_does_not_create_trip_id():
    result = infer_ticket_trip(
        trip_id=None,
        vehicle_number="DL1AA0001",
        route_label="8UP",
        transaction_timestamp="2026-10-01T08:00:00+05:30",
        timestamp_is_verified_boarding_time=False,
    )
    assert result.status == "unavailable"
    assert result.trip_id is None
    assert "not a verified boarding time" in result.reason
