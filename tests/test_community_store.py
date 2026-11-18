from datetime import UTC, datetime, timedelta

import pytest

from app.services.community_store import CommunityStore, DuplicateSubmission, RateLimitExceeded
from app.services.crowd_service import aggregate_community_reports


def test_report_duplicate_protection_and_expiry(tmp_path):
    store = CommunityStore(tmp_path / "community.sqlite3", secret="test-secret", report_ttl_seconds=60)
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    args = dict(
        stop_id="s1", stop_name="Stop one", route_id=None, category="high",
        feedback_code=None, observed_at=now, reporter_key="digest-a", network_key="net-a", now=now,
    )
    first = store.submit_report(**args)
    assert first["report_id"]
    with pytest.raises(DuplicateSubmission):
        store.submit_report(**args)
    assert len(store.recent_reports("s1", now=now + timedelta(seconds=10))) == 1
    assert store.recent_reports("s1", now=now + timedelta(seconds=61)) == []
    assert store.submit_report(**{**args, "now": now + timedelta(seconds=61)})["report_id"]


def test_rate_limit_applies_across_report_and_presence_events(tmp_path):
    store = CommunityStore(tmp_path / "community.sqlite3", secret="test-secret", network_rate_limit_per_hour=1)
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    store.submit_presence(stop_id="s1", participant_key="digest", network_key="network", now=now)
    with pytest.raises(RateLimitExceeded):
        store.submit_report(
            stop_id="s2", stop_name="Stop two", route_id=None, category="low", feedback_code=None,
            observed_at=now, reporter_key="digest-2", network_key="network", now=now,
        )


def test_crowd_aggregation_requires_sample_and_agreement():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    base = {
        "category": "high", "observed_at": now.isoformat(),
        "report_id": "r", "stop_id": "s", "stop_name": "Stop", "route_id": None,
        "feedback_code": None, "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    assert aggregate_community_reports("s", "Stop", [base, base], now=now).crowd_category is None
    result = aggregate_community_reports("s", "Stop", [base, base, base], now=now)
    assert result.status == "COMMUNITY_REPORTED"
    assert result.crowd_category == "high"
    assert result.agreement_fraction == 1.0
    assert "identities are not verified" in " ".join(result.limitations)


def test_crowd_aggregation_downweights_older_observations():
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    reports = []
    for index, (category, age) in enumerate((("high", 1100), ("high", 1100), ("low", 10))):
        reports.append({
            "category": category, "observed_at": (now - timedelta(seconds=age)).isoformat(),
            "report_id": str(index), "stop_id": "s", "stop_name": "Stop", "route_id": None,
            "feedback_code": None, "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=1)).isoformat(),
        })
    result = aggregate_community_reports("s", "Stop", reports, now=now)
    assert result.status == "COMMUNITY_REPORTED"
    assert result.crowd_category == "low"
    assert result.agreement_fraction > 0.6


def test_community_store_persists_no_raw_ip_or_location(tmp_path):
    path = tmp_path / "community.sqlite3"
    store = CommunityStore(path, secret="test-secret")
    digest = store.privacy_key("192.0.2.5", "test-agent", "presence")
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    store.submit_presence(stop_id="s1", participant_key=digest, network_key="network-digest", now=now)
    import sqlite3
    with sqlite3.connect(path) as con:
        value = con.execute("select participant_key from presence_signals").fetchone()[0]
        columns = [row[1] for row in con.execute("pragma table_info(presence_signals)")]
    assert value == digest
    assert "latitude" not in columns and "longitude" not in columns
    assert "192.0.2.5" not in value


def test_community_hmac_key_is_persistent_across_store_instances(tmp_path):
    path = tmp_path / "community.sqlite3"
    first = CommunityStore(path, secret="")
    key_a = first.privacy_key("client-token", "", "client")
    second = CommunityStore(path, secret="")
    key_b = second.privacy_key("client-token", "", "client")
    assert first.secret_is_persistent and second.secret_is_persistent
    assert key_a == key_b
    assert path.with_suffix(path.suffix + ".hmac-key").exists()
