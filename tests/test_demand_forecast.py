from datetime import date, datetime, timedelta

import duckdb
import pytest
from fastapi import HTTPException

from app.services.demand_forecast_service import forecast_ticket_activity
from scripts.backtest_ticket_activity import backtest


def _forecast_db(path):
    con = duckdb.connect(str(path))
    con.execute("create table stop_catalog(stop_id varchar, stop_name varchar)")
    con.execute("insert into stop_catalog values ('s1','Synthetic stop')")
    con.execute("create table data_quality(dataset_name varchar, dataset_max_timestamp timestamp)")
    con.execute("create table stop_demand(stop_id varchar, service_date date, day_of_week integer, transaction_hour integer, passenger_volume integer, transaction_count integer)")
    target = date(2026, 2, 10)  # Tuesday, after a four-week synthetic history.
    rows = []
    for offset, volume in zip((28, 21, 14, 7, 6, 5, 4), (10, 20, 30, 40, 8, 9, 11)):
        day = target - timedelta(days=offset)
        dow = (day.weekday() + 1) % 7
        rows.append(("s1", day, dow, 8, volume, max(1, volume // 2)))
    max_day = max(row[1] for row in rows)
    con.execute("insert into data_quality values ('etm', ?)", [datetime.combine(max_day, datetime.min.time())])
    con.executemany("insert into stop_demand values (?,?,?,?,?,?)", rows)
    con.close()
    return target


def test_forecast_uses_same_stop_weekday_hour_mean_and_labels_proxy(tmp_path, monkeypatch):
    path = tmp_path / "test.duckdb"
    target = _forecast_db(path)
    monkeypatch.setattr("app.services.demand_forecast_service.connect", lambda: duckdb.connect(str(path), read_only=True))
    result = forecast_ticket_activity(stop_id="s1", target_date=target, target_hour=8, today=date(2026, 2, 9))
    assert result.status == "PREDICTED"
    assert result.predicted_passenger_ticket_volume == 25.0
    assert result.comparable_days == 4
    assert result.prediction_type == "ticket_transaction_activity_proxy"
    assert "not a physical queue" in " ".join(result.limitations)


def test_forecast_abstains_when_source_is_stale(tmp_path, monkeypatch):
    path = tmp_path / "test.duckdb"
    _forecast_db(path)
    con = duckdb.connect(str(path))
    con.execute("update data_quality set dataset_max_timestamp=? where dataset_name='etm'", [datetime(2026, 1, 1)])
    con.close()
    monkeypatch.setattr("app.services.demand_forecast_service.connect", lambda: duckdb.connect(str(path), read_only=True))
    result = forecast_ticket_activity(stop_id="s1", target_date=date(2026, 2, 10), target_hour=8, today=date(2026, 2, 9))
    assert result.status == "STALE"
    assert result.predicted_passenger_ticket_volume is None


def test_forecast_validates_horizon_and_unknown_stop(tmp_path, monkeypatch):
    path = tmp_path / "test.duckdb"
    _forecast_db(path)
    monkeypatch.setattr("app.services.demand_forecast_service.connect", lambda: duckdb.connect(str(path), read_only=True))
    with pytest.raises(HTTPException) as exc:
        forecast_ticket_activity(stop_id="s1", target_date=date(2026, 3, 1), target_hour=8, today=date(2026, 2, 9))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        forecast_ticket_activity(stop_id="missing", target_date=date(2026, 2, 10), target_hour=8, today=date(2026, 2, 9))
    assert exc.value.status_code == 404


def test_chronological_backtest_uses_prior_windows_and_returns_real_metrics(tmp_path):
    path = tmp_path / "backtest.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create table data_quality(dataset_name varchar, source_sha256 varchar, dataset_min_timestamp timestamp, dataset_max_timestamp timestamp)")
    con.execute("insert into data_quality values ('etm','fixture-hash',timestamp '2026-01-01',timestamp '2026-01-14')")
    con.execute("create table stop_demand(stop_id varchar,service_date date,day_of_week integer,transaction_hour integer,passenger_volume integer,transaction_count integer)")
    rows = []
    start = date(2026, 1, 1)
    for index in range(14):
        day = start + timedelta(days=index)
        rows.append(("s1", day, (day.weekday() + 1) % 7, 8, 10 + index, 5 + index))
    con.executemany("insert into stop_demand values (?,?,?,?,?,?)", rows)
    con.close()
    report = backtest(path, holdout_days=7, lookback_days=7)
    assert report["data_status"] == "real_etm_historical_holdout_descriptive_only"
    assert report["passenger_volume"]["model"]["n"] == 7
    assert report["passenger_volume"]["model"]["mae"] >= 0
    assert report["transaction_count"]["baseline"]["rmse"] >= 0
