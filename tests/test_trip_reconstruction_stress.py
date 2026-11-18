from scripts.trip_reconstruction_stress_experiment import run


def test_synthetic_trip_grouping_experiment_is_reproducible_and_explicitly_synthetic():
    first = run(seed=20261117)
    second = run(seed=20261117)

    assert first == second
    assert first["status"] == "synthetic_controlled_stress_test_only"
    assert first["synthetic_records"] == 18
    assert first["synthetic_trips"] == 3
    assert first["methods"]["route_only_hour"]["false_merge_pairs"] > 0
    assert first["methods"]["vehicle_route_15min_bucket"]["false_split_pairs"] > 0


