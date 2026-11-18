from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from app.config import COMMUNITY_REPORT_TTL_SECONDS
from app.schemas import CommunityCrowdResponse

CATEGORY_ORDER = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}


def aggregate_community_reports(stop_id: str, stop_name: str, reports: list[dict], *, now: datetime) -> CommunityCrowdResponse:
    limitations = [
        "Community reports are subjective categories, not measured headcounts or onboard occupancy.",
        "Reporter identities are not verified; report count does not prove unique people.",
        "Ticketing history is not used as a substitute for a live observation.",
    ]
    if not reports:
        return CommunityCrowdResponse(
            stop_id=stop_id, stop_name=stop_name, status="UNAVAILABLE", crowd_category=None,
            report_count=0, agreement_fraction=None, evidence_quality="insufficient_reports",
            generated_at=now, freshness_seconds=None, limitations=limitations,
        )
    weighted = Counter()
    total_weight = 0.0
    for report in reports:
        observed_at = datetime.fromisoformat(report["observed_at"]).astimezone(UTC)
        age = max(0.0, (now - observed_at).total_seconds())
        weight = max(0.0, 1.0 - age / COMMUNITY_REPORT_TTL_SECONDS)
        weighted[report["category"]] += weight
        total_weight += weight
    category, category_weight = min(weighted.items(), key=lambda item: (-item[1], CATEGORY_ORDER[item[0]]))
    agreement = category_weight / total_weight if total_weight else 0.0
    latest = max(datetime.fromisoformat(report["observed_at"]) for report in reports)
    age = max(0, int((now - latest.astimezone(UTC)).total_seconds()))
    supported = len(reports) >= 3 and agreement >= 0.6
    return CommunityCrowdResponse(
        stop_id=stop_id,
        stop_name=stop_name,
        status="COMMUNITY_REPORTED" if supported else "UNAVAILABLE",
        crowd_category=category if supported else None,
        report_count=len(reports),
        agreement_fraction=round(agreement, 3),
        evidence_quality="limited_community_sample" if supported else "insufficient_reports",
        generated_at=now,
        freshness_seconds=age,
        limitations=limitations,
    )
