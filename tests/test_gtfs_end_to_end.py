from __future__ import annotations

from datetime import datetime
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

import app.services.gtfs_schedule_service as schedule_service
from app.api.routes.journeys import search
from app.schemas import JourneySearchRequest
from scripts.process_gtfs import process_gtfs


def make_synthetic_feed(path):
    files = {
        "agency.txt": "agency_name,agency_url,agency_timezone\nSynthetic Test Agency,https://example.invalid,Asia/Kolkata\n",
        "stops.txt": (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "A,Synthetic Origin,28.60,77.20\nB,Synthetic Transfer,28.61,77.21\n"
            "C,Synthetic Destination,28.62,77.22\n"
        ),
        "routes.txt": (
            "route_id,route_short_name,route_long_name,route_type\n"
            "rd,DIRECT,Synthetic Direct,3\nr1,LEG-A,Synthetic First Leg,3\n"
            "r2,LEG-B,Synthetic Second Leg,3\nrn,NIGHT,Synthetic After Midnight,3\n"
        ),
        "trips.txt": (
            "route_id,service_id,trip_id\nrd,daily,direct\nr1,daily,first\n"
            "r2,daily,second\nrn,daily,night\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "direct,08:00:00,08:00:00,A,1\ndirect,09:00:00,09:00:00,C,2\n"
            "first,08:00:00,08:00:00,A,1\nfirst,08:20:00,08:20:00,B,2\n"
            "second,08:30:00,08:30:00,B,1\nsecond,09:00:00,09:00:00,C,2\n"
            "night,24:30:00,24:30:00,A,1\nnight,25:10:00,25:10:00,C,2\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "daily,1,1,1,1,1,1,1,20261101,20261231\n"
        ),
    }
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_synthetic_gtfs_loads_and_journey_api_returns_schedule_only_options(tmp_path, monkeypatch):
    feed = tmp_path / "synthetic-only-test-fixture.zip"
    database = tmp_path / "synthetic-only-test-fixture.duckdb"
    make_synthetic_feed(feed)
    report = process_gtfs(feed, database, tmp_path / "gtfs-report.json")
    assert report["usable_for_scheduled_routing"] is True
    assert all(value == 0 for value in report["issues"].values())

    monkeypatch.setattr(schedule_service, "DATABASE_PATH", database)
    schedule_service.clear_schedule_cache()
    try:
        response = search(JourneySearchRequest(
            origin_stop_id="A",
            destination_stop_id="C",
            departure_datetime=datetime(2026, 11, 17, 0, 15),
            preference="balanced",
            max_transfers=1,
        ))
        assert response.data_status == "scheduled"
        assert response.crowd_data_available is False
        assert response.walking_connections_available is False
        assert any(option.transfers == 1 for option in response.options)
        overnight = next(option for option in response.options if option.legs[0].route_id == "rn")
        assert overnight.departure_datetime.isoformat().startswith("2026-11-17T00:30:00")
        assert overnight.arrival_datetime.isoformat().startswith("2026-11-17T01:10:00")
        assert all(option.crowd_status == "unavailable" for option in response.options)
        with pytest.raises(HTTPException) as out_of_range:
            search(JourneySearchRequest(
                origin_stop_id="A",
                destination_stop_id="C",
                departure_datetime=datetime(2027, 1, 2, 8, 0),
                preference="fastest",
                max_transfers=0,
            ))
        assert out_of_range.value.status_code == 503
        assert out_of_range.value.detail["code"] == "GTFS_SERVICE_DATE_OUT_OF_RANGE"
    finally:
        schedule_service.clear_schedule_cache()


def test_gtfs_quality_gate_rejects_duplicate_trip_stop_sequence(tmp_path):
    original = tmp_path / "synthetic-original.zip"
    invalid = tmp_path / "synthetic-duplicate-sequence.zip"
    database = tmp_path / "synthetic-invalid.duckdb"
    make_synthetic_feed(original)
    with ZipFile(original) as source, ZipFile(invalid, "w") as target:
        for name in source.namelist():
            payload = source.read(name)
            if name == "stop_times.txt":
                payload += b"first,08:01:00,08:01:00,A,1\n"
            target.writestr(name, payload)

    report = process_gtfs(invalid, database, tmp_path / "invalid-report.json")
    assert report["issues"]["duplicate_trip_stop_sequence"] > 0
    assert report["usable_for_scheduled_routing"] is False



