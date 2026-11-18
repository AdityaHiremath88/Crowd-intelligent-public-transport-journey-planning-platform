from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.routes.journeys import search
from app.schemas import JourneySearchRequest


def test_journey_api_reports_missing_gtfs_instead_of_inventing_options():
    request = JourneySearchRequest(
        origin_stop_id="unknown-a",
        destination_stop_id="unknown-b",
        departure_datetime=datetime(2026, 11, 18, 8, 0),
        preference="balanced",
    )
    with pytest.raises(HTTPException) as unavailable:
        search(request)
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["code"] == "GTFS_UNAVAILABLE"



