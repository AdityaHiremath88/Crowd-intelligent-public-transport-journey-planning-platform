from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CrowdCategory = Literal["Comfortable", "Moderate", "Crowded", "Very crowded"]


@dataclass(frozen=True)
class CrowdClassification:
    status: str
    category: CrowdCategory | None
    basis: str | None
    note: str


def classify_capacity_load(
    passenger_load: int | None,
    vehicle_capacity: int | None,
    *,
    comfortable_max_fraction: float | None = None,
    moderate_max_fraction: float | None = None,
    crowded_max_fraction: float | None = None,
) -> CrowdClassification:
    """Classify only when both verified capacity and documented thresholds are supplied."""
    values = (comfortable_max_fraction, moderate_max_fraction, crowded_max_fraction)
    if passenger_load is None or vehicle_capacity is None or vehicle_capacity <= 0 or any(v is None for v in values):
        return CrowdClassification(
            "unavailable", None, None,
            "Verified vehicle capacity, reconstructed segment load and all three documented thresholds are required.",
        )
    comfortable, moderate, crowded = (float(value) for value in values)
    if not (0 <= comfortable <= moderate <= crowded):
        return CrowdClassification("invalid_thresholds", None, None, "Thresholds must be ordered and non-negative.")
    if passenger_load < 0:
        return CrowdClassification("invalid_load", None, None, "Passenger load cannot be negative.")
    fraction = passenger_load / vehicle_capacity
    if fraction <= comfortable:
        category: CrowdCategory = "Comfortable"
    elif fraction <= moderate:
        category = "Moderate"
    elif fraction <= crowded:
        category = "Crowded"
    else:
        category = "Very crowded"
    return CrowdClassification(
        "classified", category, "capacity_fraction",
        "Classification uses caller-supplied capacity bands; it is not a legal threshold or ground-truth occupancy.",
    )


def classify_relative_load(
    passenger_load: float | None,
    *,
    comfortable_max: float | None = None,
    moderate_max: float | None = None,
    crowded_max: float | None = None,
    calibration_days: int = 0,
) -> CrowdClassification:
    """Use historically calibrated relative cutoffs; never infer them from one count."""
    thresholds = (comfortable_max, moderate_max, crowded_max)
    if passenger_load is None or any(value is None for value in thresholds) or calibration_days < 7:
        return CrowdClassification(
            "unavailable", None, None,
            "Relative bands require explicit historical cutoffs calibrated on at least seven comparable service days.",
        )
    comfortable, moderate, crowded = (float(value) for value in thresholds)
    if not (0 <= comfortable <= moderate <= crowded):
        return CrowdClassification("invalid_thresholds", None, None, "Relative cutoffs must be ordered and non-negative.")
    if passenger_load < 0:
        return CrowdClassification("invalid_load", None, None, "Passenger load cannot be negative.")
    if passenger_load <= comfortable:
        category: CrowdCategory = "Comfortable"
    elif passenger_load <= moderate:
        category = "Moderate"
    elif passenger_load <= crowded:
        category = "Crowded"
    else:
        category = "Very crowded"
    return CrowdClassification(
        "classified", category, "relative_historical_load",
        "Category is relative to the supplied comparable-day calibration; it is not an occupancy percentage.",
    )
