from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp


@dataclass(frozen=True)
class ConfidenceEvidence:
    independent_service_days: int
    coverage_fraction: float
    stop_match_quality: float | None
    route_match_quality: float | None
    trip_inference_quality: float | None
    comparable_day_consistency: float | None
    data_age_days: float


@dataclass(frozen=True)
class ConfidenceAssessment:
    status: str
    level: str | None
    score: float | None
    components: dict[str, float | None]
    note: str


def assess_confidence(evidence: ConfidenceEvidence) -> ConfidenceAssessment:
    """Explain confidence from multiple evidence dimensions; transaction count alone is excluded."""
    required = (
        evidence.stop_match_quality,
        evidence.route_match_quality,
        evidence.trip_inference_quality,
        evidence.comparable_day_consistency,
    )
    if any(value is None for value in required):
        return ConfidenceAssessment(
            "unavailable", None, None,
            {"sample_days": None, "coverage": None, "stop_match": None, "route_match": None,
             "trip_inference": None, "consistency": None, "freshness": None},
            "Confidence is unavailable because core matching, trip inference or validation evidence is missing.",
        )
    bounded = [evidence.coverage_fraction, *[float(value) for value in required]]
    if any(value < 0 or value > 1 for value in bounded) or evidence.independent_service_days < 0 or evidence.data_age_days < 0:
        return ConfidenceAssessment("invalid_evidence", None, None, {}, "Evidence values are outside their valid ranges.")
    components = {
        "sample_days": min(evidence.independent_service_days / 10, 1.0),
        "coverage": evidence.coverage_fraction,
        "stop_match": float(evidence.stop_match_quality),
        "route_match": float(evidence.route_match_quality),
        "trip_inference": float(evidence.trip_inference_quality),
        "consistency": float(evidence.comparable_day_consistency),
        "freshness": exp(-evidence.data_age_days / 30),
    }
    weights = {
        "sample_days": 0.15,
        "coverage": 0.15,
        "stop_match": 0.15,
        "route_match": 0.10,
        "trip_inference": 0.25,
        "consistency": 0.15,
        "freshness": 0.05,
    }
    score = sum(components[name] * weight for name, weight in weights.items())
    level = "low" if score < 0.45 else "medium" if score < 0.75 else "high"
    return ConfidenceAssessment(
        "assessed", level, round(score, 3), components,
        "Weighted score uses independent service days, data coverage, match quality, trip inference, comparable-day consistency and age; raw ticket count is not a confidence input.",
    )


def confidence_as_dict(assessment: ConfidenceAssessment) -> dict:
    return asdict(assessment)


