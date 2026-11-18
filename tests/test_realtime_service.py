import time

import pytest
from google.transit import gtfs_realtime_pb2

from app.services.realtime_service import RealtimeFeedError, parse_vehicle_positions


def _feed_bytes(now: int) -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = now
    entity = feed.entity.add()
    entity.id = "unknown-trip-entity"
    entity.id = "entity-1"
    vehicle = entity.vehicle
    vehicle.vehicle.id = "bus-1"
    vehicle.trip.trip_id = "trip-1"
    vehicle.trip.route_id = "route-1"
    vehicle.position.latitude = 28.61
    vehicle.position.longitude = 77.21
    vehicle.position.bearing = 90
    vehicle.timestamp = now
    vehicle.stop_id = "stop-1"
    vehicle.current_stop_sequence = 2
    return feed.SerializeToString()


def test_parse_valid_gtfs_rt_vehicle_position():
    now = int(time.time())
    parsed = parse_vehicle_positions(
        _feed_bytes(now), routes={"route-1"}, trips={"trip-1": "route-1"}, stops={"stop-1"}, now_epoch=now,
    )
    assert len(parsed["vehicles"]) == 1
    assert parsed["vehicles"][0]["vehicle_id"] == "bus-1"
    assert parsed["vehicles"][0]["route_id"] == "route-1"
    assert parsed["vehicles"][0]["route_id_matched"] is True
    assert parsed["vehicles"][0]["current_stop_id"] == "stop-1"


def test_parser_rejects_invalid_binary_and_stale_feed():
    with pytest.raises(RealtimeFeedError, match="PROTOBUF_INVALID"):
        parse_vehicle_positions(b"not protobuf", routes=set(), trips={}, stops=set())
    now = int(time.time())
    with pytest.raises(RealtimeFeedError, match="FEED_STALE"):
        parse_vehicle_positions(_feed_bytes(now - 600), routes={"route-1"}, trips={"trip-1": "route-1"},
                                 stops={"stop-1"}, now_epoch=now, max_age_seconds=60)


def test_parser_rejects_empty_feed_without_replacing_a_valid_snapshot():
    now = int(time.time())
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = now
    with pytest.raises(RealtimeFeedError, match="FEED_EMPTY"):
        parse_vehicle_positions(feed.SerializeToString(), now_epoch=now)


def test_parser_drops_stale_and_malformed_entities_and_deduplicates():
    now = int(time.time())
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = now
    for timestamp, has_position in ((now - 600, True), (now, False), (now, True), (now - 1, True)):
        entity = feed.entity.add()
        entity.id = f"e{len(feed.entity)}"
        item = entity.vehicle
        item.vehicle.id = "bus-1" if timestamp != now - 600 else "old-bus"
        item.trip.trip_id = "trip-1"
        if has_position:
            item.position.latitude = 28.6
            item.position.longitude = 77.2
            item.timestamp = timestamp
    parsed = parse_vehicle_positions(
        feed.SerializeToString(), routes={"route-1"}, trips={"trip-1": "route-1"},
        stops=set(), now_epoch=now, max_age_seconds=60,
    )
    assert len(parsed["vehicles"]) == 1
    assert parsed["vehicles"][0]["position_timestamp"] == now
    assert parsed["stale_count"] == 1
    assert parsed["malformed_count"] == 1
    assert parsed["duplicate_count"] == 1


def test_parser_rejects_unknown_trip_and_differential_feed():
    now = int(time.time())
    with pytest.raises(RealtimeFeedError, match="DIFFERENTIAL_FEED_UNSUPPORTED"):
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.DIFFERENTIAL
        parse_vehicle_positions(feed.SerializeToString(), routes=set(), trips={}, stops=set(), now_epoch=now)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = now
    entity = feed.entity.add()
    entity.id = "entity-unknown-trip"
    entity.vehicle.vehicle.id = "bus-1"
    entity.vehicle.trip.trip_id = "missing-trip"
    entity.vehicle.position.latitude = 28.6
    entity.vehicle.position.longitude = 77.2
    entity.vehicle.timestamp = now
    parsed = parse_vehicle_positions(feed.SerializeToString(), routes=set(), trips={}, stops=set(), now_epoch=now)
    assert len(parsed["vehicles"]) == 1
    assert parsed["vehicles"][0]["trip_id"] == "missing-trip"
    assert parsed["malformed_count"] == 0


def test_missing_feed_configuration_is_a_safe_unavailable_condition(monkeypatch, tmp_path):
    from app.services import realtime_service
    monkeypatch.setattr(realtime_service, "store", realtime_service.RealtimeStore(tmp_path / "rt.sqlite3"))
    monkeypatch.setattr(realtime_service, "GTFS_RT_URL", "")
    result = realtime_service.poll_once(now_epoch=int(time.time()))
    assert result == {"status": "error", "error_code": "FEED_NOT_CONFIGURED"}


def test_auth_configuration_never_requires_key_at_import_and_query_mode_fails_closed(monkeypatch):
    from app.services import realtime_service
    monkeypatch.setattr(realtime_service, "GTFS_RT_URL", "https://example.invalid/vehicle.pb")
    monkeypatch.setattr(realtime_service, "GTFS_RT_API_KEY", "")
    monkeypatch.setattr(realtime_service, "GTFS_RT_AUTH_MODE", "query")
    with pytest.raises(RealtimeFeedError, match="CREDENTIAL_MISSING"):
        realtime_service._build_request()
    monkeypatch.setattr(realtime_service, "GTFS_RT_URL", "http://example.invalid/insecure.pb")
    monkeypatch.setattr(realtime_service, "GTFS_RT_AUTH_MODE", "header")
    with pytest.raises(RealtimeFeedError, match="HTTPS_REQUIRED"):
        realtime_service._build_request()


def test_official_header_auth_and_unconfigured_status(monkeypatch, tmp_path):
    from app.services import realtime_service
    monkeypatch.setattr(realtime_service, "GTFS_RT_URL", "https://delhi.transportstack.in/api/dataset/otd/get-file?filename=VehiclePositions.pb")
    monkeypatch.setattr(realtime_service, "GTFS_RT_API_KEY", "test-only-key")
    monkeypatch.setattr(realtime_service, "GTFS_RT_AUTH_MODE", "header")
    monkeypatch.setattr(realtime_service, "GTFS_RT_AUTH_HEADER", "x-api-key")
    request = realtime_service._build_request()
    assert request.get_header("X-api-key") == "test-only-key"
    assert "test-only-key" not in request.full_url

    monkeypatch.setattr(realtime_service, "store", realtime_service.RealtimeStore(tmp_path / "rt.sqlite3"))
    monkeypatch.setattr(realtime_service, "GTFS_RT_URL", "https://delhi.transportstack.in/feed")
    monkeypatch.setattr(realtime_service, "GTFS_RT_API_KEY", "")
    status, vehicles = realtime_service.current_snapshot()
    assert status["status"] == "NOT_CONFIGURED"
    assert status["configured"] is False
    assert status["authorized"] is False
    assert vehicles == []


def test_provider_timeout_keeps_last_valid_positions_visible_as_error_cache(monkeypatch, tmp_path):
    from app.services import realtime_service
    now = int(time.time())
    store = realtime_service.RealtimeStore(tmp_path / "rt.sqlite3")
    parsed = parse_vehicle_positions(_feed_bytes(now), now_epoch=now)
    store.replace_snapshot(parsed["vehicles"], attempted_at=now, completed_at=now,
                            feed_timestamp=now, stale_count=0, malformed_count=0, duplicate_count=0)
    monkeypatch.setattr(realtime_service, "store", store)
    monkeypatch.setattr(realtime_service, "GTFS_RT_URL", "https://delhi.transportstack.in/feed")
    monkeypatch.setattr(realtime_service, "GTFS_RT_API_KEY", "test-only-key")

    class TimeoutOpener:
        def open(self, request, timeout):
            raise TimeoutError("network detail is intentionally not logged")

    monkeypatch.setattr(realtime_service.urllib.request, "build_opener", lambda *_: TimeoutOpener())
    result = realtime_service.poll_once(now_epoch=now)
    assert result == {"status": "error", "error_code": "TIMEOUT"}
    status, vehicles = realtime_service.current_snapshot()
    assert status["status"] == "ERROR"
    assert len(vehicles) == 1
    assert vehicles[0]["vehicle_id"] == "bus-1"
