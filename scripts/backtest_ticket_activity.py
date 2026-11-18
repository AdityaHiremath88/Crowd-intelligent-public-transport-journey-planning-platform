from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.config import DATABASE_PATH, PROJECT_ROOT


def backtest(database: Path = DATABASE_PATH, *, holdout_days: int = 7, lookback_days: int = 28) -> dict:
    if holdout_days < 1 or lookback_days < 7:
        raise ValueError("holdout_days must be positive and lookback_days at least 7")
    con = duckdb.connect(str(database), read_only=True)
    try:
        digest = con.execute(
            "SELECT source_sha256, dataset_min_timestamp, dataset_max_timestamp FROM data_quality WHERE dataset_name='etm'"
        ).fetchone()
        if digest is None:
            raise ValueError("ETM quality metadata is missing")
        rows = con.execute(
            f"""WITH daily AS (
                    SELECT stop_id, service_date, day_of_week, transaction_hour,
                           sum(passenger_volume)::DOUBLE AS passenger_volume,
                           sum(transaction_count)::DOUBLE AS transaction_count
                    FROM stop_demand
                    GROUP BY stop_id,service_date,day_of_week,transaction_hour
                ), latest AS (SELECT max(service_date) AS max_date FROM daily),
                scored AS (
                    SELECT d.*,
                           avg(passenger_volume) OVER (
                               PARTITION BY stop_id,day_of_week,transaction_hour ORDER BY service_date
                               RANGE BETWEEN INTERVAL {lookback_days} DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
                           ) AS model_volume,
                           avg(transaction_count) OVER (
                               PARTITION BY stop_id,day_of_week,transaction_hour ORDER BY service_date
                               RANGE BETWEEN INTERVAL {lookback_days} DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
                           ) AS model_transactions,
                           avg(passenger_volume) OVER (
                               PARTITION BY stop_id,transaction_hour ORDER BY service_date
                               RANGE BETWEEN INTERVAL {lookback_days} DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
                           ) AS baseline_volume,
                           avg(transaction_count) OVER (
                               PARTITION BY stop_id,transaction_hour ORDER BY service_date
                               RANGE BETWEEN INTERVAL {lookback_days} DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
                           ) AS baseline_transactions,
                           (SELECT max_date FROM latest) AS max_date
                    FROM daily d
                )
                SELECT service_date,passenger_volume,transaction_count,model_volume,model_transactions,
                       baseline_volume,baseline_transactions
                FROM scored WHERE service_date > max_date - INTERVAL {holdout_days} DAY
                  AND model_volume IS NOT NULL AND baseline_volume IS NOT NULL"""
        ).fetchall()
    finally:
        con.close()

    def metrics(actual_column: int, model_column: int) -> dict:
        if not rows:
            return {"n": 0, "mae": None, "rmse": None}
        errors = [float(row[model_column]) - float(row[actual_column]) for row in rows]
        return {
            "n": len(errors),
            "mae": round(sum(abs(error) for error in errors) / len(errors), 4),
            "rmse": round((sum(error * error for error in errors) / len(errors)) ** 0.5, 4),
        }

    model_volume = metrics(1, 3)
    baseline_volume = metrics(1, 5)
    model_tx = metrics(2, 4)
    baseline_tx = metrics(2, 6)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_status": "real_etm_historical_holdout_descriptive_only",
        "source_sha256": digest[0],
        "source_start": str(digest[1]), "source_end": str(digest[2]),
        "holdout_days": holdout_days, "lookback_days": lookback_days,
        "target": "daily per-stop x transaction-hour ticket-origin aggregates on dates with at least one source row",
        "model": "mean of prior observations with same stop label, weekday and transaction hour",
        "baseline": "mean of prior observations with same stop label and transaction hour, ignoring weekday",
        "passenger_volume": {"model": model_volume, "baseline": baseline_volume},
        "transaction_count": {"model": model_tx, "baseline": baseline_tx},
        "limitations": [
            "This evaluates ticket transaction activity/passenger volume represented by tickets, not passengers physically waiting or onboard.",
            "Rows with no source tickets in a stop-hour are not treated as verified zero service/demand, so evaluation is conditional on observed positive cells.",
            "Only one month is available; results are a small chronological in-month holdout, not seasonal or future-period validation.",
            "Stop labels are not verified physical-stop IDs and transaction time is not boarding time.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronological baseline backtest for ETM ticket activity proxies.")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--holdout-days", type=int, default=7)
    parser.add_argument("--lookback-days", type=int, default=28)
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "outputs" / "ticket_activity_backtest.json")
    args = parser.parse_args()
    result = backtest(args.database.resolve(), holdout_days=args.holdout_days, lookback_days=args.lookback_days)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()


