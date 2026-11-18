"""Controlled synthetic stress test for ticket-to-trip grouping heuristics.

This experiment quantifies sensitivity to missing vehicle IDs and event timestamps.
It is not a model of Delhi operations and its metrics are not real-world accuracy.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

MISSING_VEHICLE_RATE = 1_242_167 / 2_559_899


def _pairwise_metrics(truth: list[str], predicted: list[str]) -> dict[str, float]:
    truth_pairs = set()
    predicted_pairs = set()
    for i in range(len(truth)):
        for j in range(i + 1, len(truth)):
            if truth[i] == truth[j]:
                truth_pairs.add((i, j))
            if predicted[i] == predicted[j]:
                predicted_pairs.add((i, j))
    tp = len(truth_pairs & predicted_pairs)
    precision = tp / len(predicted_pairs) if predicted_pairs else 1.0
    recall = tp / len(truth_pairs) if truth_pairs else 1.0
    return {
        "pairwise_precision": precision,
        "pairwise_recall": recall,
        "pairwise_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "false_merge_pairs": len(predicted_pairs - truth_pairs),
        "false_split_pairs": len(truth_pairs - predicted_pairs),
    }


def run(seed: int = 20261117) -> dict:
    rng = random.Random(seed)
    rows = []
    # Three distinct runs share the same route and clock hour; each run has six
    # events distributed over 25 minutes, deliberately crossing 15-minute bins.
    for trip_no, (vehicle, start_minute) in enumerate((("V-A", 5), ("V-B", 7), ("V-A", 34))):
        for event in range(6):
            rows.append({
                "truth": f"trip-{trip_no}", "route": "R-SYNTHETIC-UP",
                "vehicle": vehicle, "minute": start_minute + event * 5,
            })
    missing_indices = set(rng.sample(range(len(rows)), round(len(rows) * MISSING_VEHICLE_RATE)))
    for index, row in enumerate(rows):
        row["observed_vehicle"] = None if index in missing_indices else row["vehicle"]
        # Transaction time is not boarding time. Apply a controlled nonnegative
        # recording delay, intentionally varying by event.
        row["transaction_minute"] = row["minute"] + rng.choice((0, 3, 12, 27))

    truth = [row["truth"] for row in rows]
    methods = {}
    for name, grouper in {
        "route_only_hour": lambda r: (r["route"], r["transaction_minute"] // 60),
        "vehicle_route_hour": lambda r: (r["route"], r["observed_vehicle"] or "UNKNOWN", r["transaction_minute"] // 60),
        "vehicle_route_15min_bucket": lambda r: (
            r["route"], r["observed_vehicle"] or "UNKNOWN", r["transaction_minute"] // 15
        ),
    }.items():
        groups = [str(grouper(row)) for row in rows]
        methods[name] = _pairwise_metrics(truth, groups)

    return {
        "status": "synthetic_controlled_stress_test_only",
        "seed": seed,
        "synthetic_records": len(rows),
        "synthetic_trips": len(set(truth)),
        "vehicle_id_missing_fraction": sum(r["observed_vehicle"] is None for r in rows) / len(rows),
        "reference_missing_vehicle_fraction_from_actual_etm": MISSING_VEHICLE_RATE,
        "transaction_time_delay_minutes": "synthetically sampled from {0, 3, 12, 27}; not fitted to ETM because boarding delay is unobserved",
        "methods": methods,
        "interpretation": "Metrics demonstrate that simple keys can merge or split constructed runs. Synthetic truth is known by construction and does not establish Delhi trip reconstruction performance.",
    }


if __name__ == "__main__":
    result = run()
    output = Path("outputs/trip_reconstruction_stress_experiment.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
