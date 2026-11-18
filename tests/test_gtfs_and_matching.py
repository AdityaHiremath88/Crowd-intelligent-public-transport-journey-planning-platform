from __future__ import annotations

import zipfile

import pytest

from app.data_pipeline.gtfs_loader import inspect_gtfs, parse_gtfs_time
from app.data_pipeline.route_matcher import candidates_for_route
from app.data_pipeline.stop_matcher import candidates_for_stop


def test_gtfs_time_supports_after_midnight_service():
    assert parse_gtfs_time("25:10:05") == 25 * 3600 + 10 * 60 + 5


@pytest.mark.parametrize("value", ["10:60:00", "10:00", "-1:00:00", "aa:00:00"])
def test_gtfs_time_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_gtfs_time(value)


def test_gtfs_audit_reports_missing_stop_times(tmp_path):
    archive_path = tmp_path / "partial.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\ns1,A,1,1\n")
    audit = inspect_gtfs(archive_path)
    assert "stop_times.txt" in audit.missing_required_files
    assert audit.usable_for_scheduled_routing is False


def test_gtfs_audit_requires_a_route_name_field(tmp_path):
    archive_path = tmp_path / "routes-without-names.zip"
    files = {
        "agency.txt": "agency_name,agency_url,agency_timezone\nA,https://example.invalid,Asia/Kolkata\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\ns,A,1,1\n",
        "routes.txt": "route_id,route_type\nr,3\n",
        "trips.txt": "route_id,service_id,trip_id\nr,s,t\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt,08:00:00,08:00:00,s,1\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\ns,1,1,1,1,1,1,1,20260101,20261231\n",
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    audit = inspect_gtfs(archive_path)
    assert "route_short_name or route_long_name" in audit.missing_columns["routes.txt"]
    assert audit.usable_for_scheduled_routing is False


def test_fuzzy_match_is_only_a_manual_review_candidate():
    result = candidates_for_stop("Kashmere Gate Metro", [("s1", "Kashmere Gate")])
    assert result[0].match_method == "fuzzy_candidate"
    assert result[0].review_status == "manual_review"


def test_duplicate_exact_matches_are_not_auto_resolved():
    result = candidates_for_stop("Central Stop", [("s1", "Central Stop"), ("s2", "Central Stop")])
    assert len(result) == 2
    assert all(row.review_status == "manual_review" for row in result)


def test_fuzzy_route_candidate_is_not_accepted_automatically():
    result = candidates_for_route("717A UP", [("route-1", "717AUP", "")])
    assert result[0].match_method == "exact_unique"
    assert result[0].review_status == "needs_direction_review"


def test_fuzzy_route_match_requires_manual_review():
    result = candidates_for_route("717AUPX", [("route-1", "717AUP", "")])
    assert result[0].match_method == "fuzzy_candidate"
    assert result[0].review_status == "manual_review"



