from __future__ import annotations

from datetime import date

import duckdb
import pytest
from fastapi import HTTPException

import app.database as database
from app.api.routes import analytics, stops
from app.api.routes import routes as route_api, system


@pytest.fixture
def analytics_db(tmp_path, monkeypatch):
    path = tmp_path / "api-fixture.duckdb"
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE data_quality AS SELECT
            'etm' dataset_name, 4::BIGINT dataset_rows, 4::BIGINT retained_rows,
            0::BIGINT excluded_rows,
            TIMESTAMPTZ '2026-10-05 08:00:00+05:30' dataset_min_timestamp,
            TIMESTAMPTZ '2026-10-06 09:00:00+05:30' dataset_max_timestamp,
            TIMESTAMPTZ '2026-11-01 00:00:00+00:00' generated_at,
            2::BIGINT distinct_routes, 2::BIGINT distinct_vehicles,
            2::BIGINT distinct_start_stops, 2::BIGINT distinct_end_stops,
            1::BIGINT null_vehicle_rows, 0::BIGINT invalid_passenger_rows,
            0::BIGINT exact_duplicate_rows, 10::BIGINT passenger_volume_total,
            2.5::DOUBLE passenger_count_mean, 0::BIGINT null_start_stop_rows,
            0::BIGINT null_end_stop_rows, 0::BIGINT null_route_rows
    """)
    con.execute("CREATE TABLE stop_catalog(stop_id VARCHAR, stop_name VARCHAR)")
    con.execute("CREATE TABLE etm_records(passenger_count BIGINT)")
    con.execute("CREATE TABLE service_profile(service_date DATE, transaction_hour INTEGER, is_ac BOOLEAN, ticket_type_id INTEGER, passenger_volume BIGINT, transaction_count BIGINT)")
    con.executemany(
        "INSERT INTO service_profile VALUES (?, ?, ?, ?, ?, ?)",
        [(date(2026, 10, 5), 8, True, 1, 4, 3), (date(2026, 10, 5), 9, True, 1, 2, 2)],
    )
    con.execute("CREATE TABLE route_demand(route VARCHAR, service_date DATE, transaction_hour INTEGER, day_of_week INTEGER, passenger_volume BIGINT, transaction_count BIGINT)")
    con.executemany(
        "INSERT INTO route_demand VALUES (?, ?, ?, ?, ?, ?)",
        [("8UP", date(2026, 10, 5), 8, 1, 4, 3), ("8UP", date(2026, 10, 5), 9, 1, 2, 2),
         ("8UP", date(2026, 10, 10), 10, 6, 1, 1), ("9DOWN", date(2026, 10, 6), 9, 2, 3, 2)],
    )
    con.execute("CREATE TABLE route_stop_catalog(route VARCHAR, start_stop_name VARCHAR)")
    con.executemany("INSERT INTO route_stop_catalog VALUES (?, ?)", [("8UP", "Alpha"), ("8UP", "Beta")])
    con.executemany("INSERT INTO stop_catalog VALUES (?, ?)", [("etm_a", "Alpha Stop"), ("etm_b", "Beta / Stop")])
    con.execute("""
        CREATE TABLE stop_demand(
            stop_id VARCHAR, stop_name VARCHAR, route VARCHAR, day_of_week INTEGER,
            transaction_hour INTEGER, service_date DATE, passenger_volume BIGINT,
            transaction_count BIGINT
        )
    """)
    con.executemany(
        "INSERT INTO stop_demand VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("etm_a", "Alpha Stop", "8UP", 1, 8, date(2026, 10, 5), 4, 3),
            ("etm_a", "Alpha Stop", "8UP", 1, 9, date(2026, 10, 5), 2, 2),
            ("etm_a", "Alpha Stop", "9DOWN", 2, 9, date(2026, 10, 6), 3, 2),
            ("etm_b", "Beta / Stop", "8UP", 6, 10, date(2026, 10, 10), 1, 1),
        ],
    )
    con.execute("""
        CREATE TABLE daily_demand AS
        SELECT service_date, sum(passenger_volume)::BIGINT passenger_volume,
               sum(transaction_count)::BIGINT transaction_count
        FROM stop_demand GROUP BY service_date
    """)
    con.execute("""
        CREATE TABLE hourly_demand AS
        SELECT service_date, transaction_hour, day_of_week,
               sum(passenger_volume)::BIGINT passenger_volume,
               sum(transaction_count)::BIGINT transaction_count
        FROM stop_demand GROUP BY ALL
    """)
    con.close()
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    return path


def test_stop_search_details_and_demand_filters(analytics_db):
    result = stops.list_stops(q="beta", limit=10)
    assert result["items"] == [{
        "id": "etm_b", "stop_name": "Beta / Stop", "coordinates": None, "demand_available": True
    }]
    detail = stops.stop_detail("etm_b")
    assert detail["routes_observed"] == 1
    assert detail["passenger_volume"] == 1

    demand = stops.stop_demand(
        "etm_a", route="8UP", day_of_week=1, transaction_hour=8,
        date_from=date(2026, 10, 5), date_to=date(2026, 10, 5),
    )
    assert demand["passenger_volume"] == 4
    assert demand["transaction_count"] == 3
    assert demand["days_covered"] == 1
    assert demand["timestamp_basis"].startswith("ticket transaction time")


def test_unknown_stop_and_reversed_date_range_return_404_and_422(analytics_db):
    with pytest.raises(HTTPException) as unknown:
        stops.stop_detail("missing")
    assert unknown.value.status_code == 404
    with pytest.raises(HTTPException) as reversed_range:
        stops.stop_demand("etm_a", date_from=date(2026, 10, 7), date_to=date(2026, 10, 1))
    assert reversed_range.value.status_code == 422


def test_map_and_gtfs_stop_search_are_unavailable_without_a_feed(analytics_db):
    with pytest.raises(HTTPException) as missing_feed:
        stops.map_stops(south=28.4, west=76.8, north=28.9, east=77.5, limit=100)
    assert missing_feed.value.status_code == 503
    with pytest.raises(HTTPException) as missing_stops:
        stops.list_stops(q="Alpha", limit=10, source="gtfs")
    assert missing_stops.value.status_code == 503


def test_nearby_stop_uses_one_time_coordinates_and_returns_real_gtfs_identity(analytics_db, monkeypatch):
    con = duckdb.connect(str(analytics_db))
    con.execute("CREATE TABLE gtfs_stops(stop_id VARCHAR, stop_name VARCHAR, stop_lat VARCHAR, stop_lon VARCHAR)")
    con.executemany("INSERT INTO gtfs_stops VALUES (?, ?, ?, ?)", [
        ("stop-near", "Near Stop", "28.6101", "77.2101"),
        ("stop-far", "Far Stop", "28.7000", "77.3000"),
    ])
    con.close()
    monkeypatch.setattr(stops, "gtfs_is_usable", lambda _: True)
    from app.schemas import NearbyStopRequest
    result = stops.nearby_stops(NearbyStopRequest(latitude=28.61, longitude=77.21))
    assert result["items"][0]["id"] == "stop-near"
    assert result["items"][0]["distance_meters"] < 100
    assert "not stored" in result["privacy_note"]


def test_historical_analytics_return_recorded_volume(analytics_db):
    overview = analytics.overview()
    assert overview["dataset_rows"] == 4
    assert overview["occupancy_predictions"] == "unavailable"

    daily = analytics.trends("day", date(2026, 10, 5), date(2026, 10, 6))
    assert [point["passenger_volume"] for point in daily["points"]] == [6, 3]
    weekly = analytics.trends("week")
    assert len(weekly["points"]) == 1

    peak = analytics.peak_hours("weekday")
    assert peak["hours"][0]["transaction_hour"] == 9
    assert peak["hours"][0]["passenger_volume"] == 5

    route_summary = analytics.corridors(limit=1)
    assert route_summary["routes"][0]["route"] == "8UP"
    assert route_summary["routes"][0]["passenger_volume"] == 7


def test_system_metadata_reports_only_capabilities_supported_by_loaded_data(analytics_db):
    caps = system.capabilities()
    assert caps.historical_ticket_analytics is True
    assert caps.scheduled_journey_search is False
    assert caps.trip_level_load_estimation is False
    assert caps.crowd_classification is False
    catalog = system.datasets()
    assert [item.dataset_name for item in catalog.datasets] == ["etm"]
    methodology = system.methodology()
    assert "physical queue count" in methodology.historical_demand


def test_route_label_catalog_and_profiles_keep_ticket_volume_distinct(analytics_db):
    catalog = route_api.list_routes(q="8", limit=10, offset=0)
    assert catalog["items"][0]["route_label"] == "8UP"
    assert catalog["items"][0]["passenger_volume"] == 7
    assert catalog["items"][0]["transaction_count"] == 6
    assert catalog["items"][0]["start_label_count"] == 2
    profile = route_api.route_profile("8UP")
    assert profile["passenger_volume"] == 7
    assert profile["transaction_count"] == 6
    assert profile["start_label_count"] == 2
    assert [row["transaction_hour"] for row in profile["hourly_profile"]] == [8, 9, 10]


def test_service_profile_keeps_source_category_fields_uninterpreted(analytics_db):
    result = analytics.service_profile()
    assert result["groups"][0]["is_ac"] is True
    assert result["groups"][0]["passenger_volume"] == 6
    assert "business definitions" in result["semantic_caveat"]
