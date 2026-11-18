from __future__ import annotations

from datetime import date

from app.routing.journey_search import (
    ScheduledTrip,
    StopEvent,
    active_services_for_date,
    build_journey_search_index,
    search_journeys,
    trip_from_gtfs_rows,
)
from app.routing.ranking import rank_journeys


def event(stop, name, sequence, arrival, departure):
    return StopEvent(stop, name, sequence, arrival, departure)


def test_active_service_uses_calendar_and_exceptions():
    calendar = [{
        "service_id": "weekday", "start_date": "20261101", "end_date": "20261130",
        "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1",
        "friday": "1", "saturday": "0", "sunday": "0",
    }]
    exceptions = [{"service_id": "weekday", "date": "20261117", "exception_type": "2"}]
    assert active_services_for_date(date(2026, 11, 16), calendar) == {"weekday"}
    assert active_services_for_date(date(2026, 11, 17), calendar, exceptions) == set()


def test_trip_parser_keeps_after_midnight_gtfs_times():
    trip = trip_from_gtfs_rows(
        {"trip_id": "t1", "route_id": "r1", "service_id": "s1"},
        [
            {"stop_id": "b", "stop_sequence": "2", "arrival_time": "24:20:00", "departure_time": "24:20:00"},
            {"stop_id": "a", "stop_sequence": "1", "arrival_time": "24:00:00", "departure_time": "24:00:00"},
        ],
    )
    assert trip.events[0].stop_id == "a"
    assert trip.events[0].departure_seconds == 24 * 3600


def test_search_returns_direct_and_one_transfer_schedules():
    direct = ScheduledTrip("direct", "r0", "svc", (
        event("A", "Origin", 1, 8 * 3600, 8 * 3600),
        event("C", "Destination", 2, 9 * 3600, 9 * 3600),
    ))
    first = ScheduledTrip("first", "r1", "svc", (
        event("A", "Origin", 1, 8 * 3600, 8 * 3600),
        event("B", "Transfer", 2, 8 * 3600 + 1200, 8 * 3600 + 1200),
    ))
    second = ScheduledTrip("second", "r2", "svc", (
        event("B", "Transfer", 1, 8 * 3600 + 1800, 8 * 3600 + 1800),
        event("C", "Destination", 2, 9 * 3600, 9 * 3600),
    ))
    options = search_journeys([direct, first, second], "A", "C", 8 * 3600, {"svc"})
    assert options[0].legs[0].trip_id == "direct"
    assert any(option.transfers == 1 and option.transfer_stops == ("Transfer",) for option in options)
    assert all(option.crowd_status == "unavailable" for option in options)
    assert all(option.eta_source == "GTFS scheduled times (approximate)" for option in options)
    indexed = search_journeys(
        [direct, first, second], "A", "C", 8 * 3600, {"svc"},
        search_index=build_journey_search_index([direct, first, second]),
    )
    assert indexed == options


def test_search_respects_active_service_and_transfer_buffer():
    first = ScheduledTrip("first", "r1", "weekday", (
        event("A", "Origin", 1, 8 * 3600, 8 * 3600),
        event("B", "Transfer", 2, 8 * 3600 + 600, 8 * 3600 + 600),
    ))
    second = ScheduledTrip("second", "r2", "weekend", (
        event("B", "Transfer", 1, 8 * 3600 + 700, 8 * 3600 + 700),
        event("C", "Destination", 2, 9 * 3600, 9 * 3600),
    ))
    assert search_journeys([first, second], "A", "C", 8 * 3600, {"weekday", "weekend"}, min_transfer_seconds=300) == []
    assert search_journeys([first, second], "A", "C", 8 * 3600, {"weekday"}) == []


def test_search_supports_two_feasible_transfers():
    trips = [
        ScheduledTrip("leg1", "r1", "svc", (event("A", "A", 1, 100, 100), event("B", "B", 2, 300, 300))),
        ScheduledTrip("leg2", "r2", "svc", (event("B", "B", 1, 600, 600), event("C", "C", 2, 800, 800))),
        ScheduledTrip("leg3", "r3", "svc", (event("C", "C", 1, 1100, 1100), event("D", "D", 2, 1400, 1400))),
    ]
    options = search_journeys(trips, "A", "D", 0, {"svc"}, max_transfers=2)
    result = next(option for option in options if option.transfers == 2)
    assert [leg.trip_id for leg in result.legs] == ["leg1", "leg2", "leg3"]
    assert result.transfer_stops == ("B", "C")


def test_search_reconstructs_three_transfer_itinerary_and_stops():
    stops = ["A", "B", "C", "D", "E"]
    trips = [
        ScheduledTrip(f"leg{i}", f"r{i}", "svc", (
            event(stops[i], stops[i], 1, i * 600, i * 600),
            event(stops[i + 1], stops[i + 1], 2, i * 600 + 300, i * 600 + 300),
        ))
        for i in range(4)
    ]
    result = next(
        option for option in search_journeys(trips, "A", "E", 0, {"svc"}, max_transfers=3)
        if option.transfers == 3
    )
    assert [leg.trip_id for leg in result.legs] == ["leg0", "leg1", "leg2", "leg3"]
    assert [stop for leg in result.legs for stop in leg.stop_sequence] == ["A", "B", "B", "C", "C", "D", "D", "E"]
    assert result.transfer_stops == ("B", "C", "D")


def test_search_returns_no_journey_for_missing_or_inactive_stops():
    trip = ScheduledTrip("t", "r", "svc", (
        event("A", "A", 1, 0, 0), event("B", "B", 2, 300, 300),
    ))
    assert search_journeys([trip], "UNKNOWN", "B", 0, {"svc"}) == []
    assert search_journeys([trip], "A", "B", 0, {"other"}) == []


def test_trip_parser_rejects_duplicate_stop_sequences():
    import pytest

    with pytest.raises(ValueError, match="non-increasing stop_sequence"):
        trip_from_gtfs_rows(
            {"trip_id": "dup", "route_id": "r", "service_id": "s"},
            [
                {"stop_id": "A", "stop_sequence": "1", "arrival_time": "08:00:00", "departure_time": "08:00:00"},
                {"stop_id": "B", "stop_sequence": "1", "arrival_time": "08:05:00", "departure_time": "08:05:00"},
            ],
        )


def test_search_rejects_transfer_count_above_documented_limit():
    import pytest

    with pytest.raises(ValueError, match="at most three transfers"):
        search_journeys([], "A", "B", 0, set(), max_transfers=4)


def test_comfort_ranking_can_favor_direct_when_crowd_is_unknown():
    direct = search_journeys(
        [ScheduledTrip("direct", "r0", "svc", (
            event("A", "Origin", 1, 0, 0), event("C", "Destination", 2, 3600, 3600),
        ))],
        "A", "C", 0, {"svc"}, max_transfers=1,
    )
    transfer = ScheduledTrip("transfer", "r1", "svc", (
        event("A", "Origin", 1, 0, 0), event("B", "Transfer", 2, 300, 300),
    ))
    onward = ScheduledTrip("onward", "r2", "svc", (
        event("B", "Transfer", 1, 600, 600), event("C", "Destination", 2, 1200, 1200),
    ))
    both = search_journeys([transfer, onward], "A", "C", 0, {"svc"})
    options = rank_journeys(direct + both, "comfort")
    assert options[0].legs[0].trip_id == "direct"
    assert all(dict(option.score_components)["crowd"] is None for option in options)
    assert all(option.crowd_status == "unavailable" for option in options)


def test_ranking_time_component_includes_wait_before_first_bus():
    early_short = ScheduledTrip("early", "r1", "svc", (
        event("A", "Origin", 1, 600, 600), event("C", "Destination", 2, 1200, 1200),
    ))
    later_fast = ScheduledTrip("later", "r2", "svc", (
        event("A", "Origin", 1, 900, 900), event("C", "Destination", 2, 1100, 1100),
    ))
    options = search_journeys([early_short, later_fast], "A", "C", 0, {"svc"})
    ranked = rank_journeys(options, "fastest", requested_departure_seconds=0)
    assert ranked[0].legs[0].trip_id == "later"



