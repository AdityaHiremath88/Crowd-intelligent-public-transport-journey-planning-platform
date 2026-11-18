from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException

from app.routing.journey_search import active_services_for_date, search_journeys
from app.routing.ranking import rank_journeys
from app.schemas import (
    JourneyLegResponse,
    JourneyOptionResponse,
    JourneySearchRequest,
    JourneySearchResponse,
    JourneyStop,
)
from app.services.gtfs_schedule_service import load_schedule_data

router = APIRouter(prefix="/journeys", tags=["journeys"])
EARLY_SERVICE_CUTOFF_SECONDS = 6 * 60 * 60


@router.post("/search", response_model=JourneySearchResponse)
def search(request: JourneySearchRequest) -> JourneySearchResponse:
    if request.origin_stop_id == request.destination_stop_id:
        raise HTTPException(status_code=422, detail="Origin and destination must be different stops")
    try:
        schedule = load_schedule_data()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Processed DuckDB database is unavailable") from exc
    if schedule is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "GTFS_UNAVAILABLE",
                "message": "Journey search needs a validated GTFS static feed. No usable feed is loaded.",
            },
        )
    if request.origin_stop_id not in schedule.stop_names:
        raise HTTPException(status_code=404, detail=f"Unknown GTFS origin stop: {request.origin_stop_id}")
    if request.destination_stop_id not in schedule.stop_names:
        raise HTTPException(status_code=404, detail=f"Unknown GTFS destination stop: {request.destination_stop_id}")
    try:
        timezone = ZoneInfo(schedule.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        timezone = ZoneInfo("Asia/Kolkata")
    departure = request.departure_datetime
    departure = departure.replace(tzinfo=timezone) if departure.tzinfo is None else departure.astimezone(timezone)
    if (
        schedule.service_start_date is not None
        and schedule.service_end_date is not None
        and not schedule.service_start_date <= departure.date() <= schedule.service_end_date
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "GTFS_SERVICE_DATE_OUT_OF_RANGE",
                "message": "The loaded static GTFS calendar does not cover the requested local service date.",
                "service_start_date": schedule.service_start_date.isoformat(),
                "service_end_date": schedule.service_end_date.isoformat(),
            },
        )
    departure_seconds = departure.hour * 3600 + departure.minute * 60 + departure.second

    candidates = []
    current_services = active_services_for_date(departure.date(), schedule.calendar_rows, schedule.exception_rows)
    candidates.extend(
        search_journeys(
            schedule.trips,
            request.origin_stop_id,
            request.destination_stop_id,
            departure_seconds,
            current_services,
            max_transfers=request.max_transfers,
            search_index=schedule.search_index,
        )
    )
    # Standard GTFS may represent after-midnight service as 24:xx on the prior service day.
    if departure_seconds < EARLY_SERVICE_CUTOFF_SECONDS:
        previous_date = departure.date() - timedelta(days=1)
        previous_services = active_services_for_date(previous_date, schedule.calendar_rows, schedule.exception_rows)
        prior_day = search_journeys(
            schedule.trips,
            request.origin_stop_id,
            request.destination_stop_id,
            departure_seconds + 24 * 60 * 60,
            previous_services,
            max_transfers=request.max_transfers,
            search_index=schedule.search_index,
        )
        candidates.extend(
            replace(
                option,
                departure_seconds=option.departure_seconds - 24 * 60 * 60,
                arrival_seconds=option.arrival_seconds - 24 * 60 * 60,
                legs=tuple(
                    replace(
                        leg,
                        departure_seconds=leg.departure_seconds - 24 * 60 * 60,
                        arrival_seconds=leg.arrival_seconds - 24 * 60 * 60,
                    )
                    for leg in option.legs
                ),
            )
            for option in prior_day
        )

    deduplicated = {}
    for option in candidates:
        key = (tuple(leg.trip_id for leg in option.legs), option.departure_seconds, option.arrival_seconds)
        deduplicated[key] = option
    ranked = rank_journeys(
        list(deduplicated.values()), request.preference, request.max_transfers, departure_seconds
    )[:10]
    midnight = datetime.combine(departure.date(), time.min, tzinfo=timezone)

    def clock_time(seconds: int) -> datetime:
        return midnight + timedelta(seconds=seconds)

    options = []
    for option in ranked:
        total_wait = max(0, option.departure_seconds - departure_seconds)
        for previous, following in zip(option.legs, option.legs[1:]):
            total_wait += max(0, following.departure_seconds - previous.arrival_seconds)
        leg_responses = [
            JourneyLegResponse(
                trip_id=leg.trip_id,
                route_id=leg.route_id,
                route_name=schedule.route_labels.get(leg.route_id, leg.route_id),
                from_stop=JourneyStop(stop_id=leg.from_stop_id, stop_name=leg.from_stop_name),
                to_stop=JourneyStop(stop_id=leg.to_stop_id, stop_name=leg.to_stop_name),
                departure_datetime=clock_time(leg.departure_seconds),
                arrival_datetime=clock_time(leg.arrival_seconds),
                stop_sequence=list(leg.stop_sequence),
            )
            for leg in option.legs
        ]
        options.append(
            JourneyOptionResponse(
                legs=leg_responses,
                departure_datetime=clock_time(option.departure_seconds),
                arrival_datetime=clock_time(option.arrival_seconds),
                duration_seconds=option.duration_seconds,
                waiting_seconds=total_wait,
                transfers=option.transfers,
                transfer_stops=list(option.transfer_stops),
                eta_source=option.eta_source,
                score=option.score or 0.0,
                score_components=dict(option.score_components),
            )
        )

    ranking_note = (
        "Crowd estimates are unavailable. This ranking renormalizes the configured time and transfer weights; "
        "comfort preference cannot yet optimize for crowd exposure."
    )
    return JourneySearchResponse(
        options=options,
        origin_stop_id=request.origin_stop_id,
        destination_stop_id=request.destination_stop_id,
        preference=request.preference,
        data_source="loaded GTFS static schedule",
        data_status="scheduled",
        generated_at=datetime.now(UTC),
        crowd_data_available=False,
        ranking_note=ranking_note,
        walking_connections_available=False,
        message=None if options else "No scheduled journey was found for this departure and service date.",
    )



