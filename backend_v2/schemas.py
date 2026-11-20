from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StopItem(BaseModel):
    stop_id: str
    stop_name: str
    latitude: float | None
    longitude: float | None
    coordinate_source: Literal["gtfs_publisher_unverified"] = "gtfs_publisher_unverified"


class StopSearchResponse(BaseModel):
    items: list[StopItem]
    source: Literal["GTFS static feed"] = "GTFS static feed"
    offset: int
    total_returned: int
    next_offset: int | None


class JourneySearchRequest(BaseModel):
    origin_stop_id: str = Field(min_length=1, max_length=128)
    destination_stop_id: str = Field(min_length=1, max_length=128)
    departure_datetime: datetime
    preference: Literal["fastest", "balanced", "comfort"] = "balanced"
    max_transfers: int = Field(default=1, ge=0, le=3)

    @model_validator(mode="after")
    def different_stops(self) -> "JourneySearchRequest":
        if self.origin_stop_id == self.destination_stop_id:
            raise ValueError("Origin and destination must be different stops")
        return self


class JourneyStop(BaseModel):
    stop_id: str
    stop_name: str


class JourneyLeg(BaseModel):
    trip_id: str
    route_id: str
    route_name: str
    from_stop: JourneyStop
    to_stop: JourneyStop
    departure_datetime: datetime
    arrival_datetime: datetime
    stop_sequence: list[str]
    eta_source: Literal["GTFS static schedule"] = "GTFS static schedule"


class JourneyOption(BaseModel):
    legs: list[JourneyLeg]
    departure_datetime: datetime
    arrival_datetime: datetime
    duration_seconds: int
    waiting_seconds: int
    transfers: int
    transfer_stops: list[str]
    eta_source: Literal["GTFS static schedule"] = "GTFS static schedule"
    crowd_status: Literal["unavailable"] = "unavailable"
    score: float
    score_components: dict[str, float | None]


class JourneySearchResponse(BaseModel):
    options: list[JourneyOption]
    origin_stop_id: str
    destination_stop_id: str
    preference: Literal["fastest", "balanced", "comfort"]
    data_source: Literal["GTFS static schedule"] = "GTFS static schedule"
    data_status: Literal["scheduled"] = "scheduled"
    generated_at: datetime
    crowd_data_available: Literal[False] = False
    ranking_note: str
    walking_connections_available: Literal[False] = False
    message: str | None = None


class RouteActivityObservation(BaseModel):
    date: date
    passenger_volume: int
    transaction_count: int


class RouteActivityResponse(BaseModel):
    route_id: str
    route_label: str
    target_date: date
    transaction_hour: int
    weekday: str
    status: Literal["available", "insufficient_history", "unavailable"]
    metric: Literal["historical_ticket_activity"] = "historical_ticket_activity"
    matching_basis: Literal["same route label candidate, weekday, and transaction hour"] = "same route label candidate, weekday, and transaction hour"
    comparable_day_count: int
    average_passenger_volume: float | None
    average_transaction_count: float | None
    observations: list[RouteActivityObservation]
    source: Literal["October 2026 ETM ticket records"] = "October 2026 ETM ticket records"
    timestamp_basis: Literal["ticket transaction time; not confirmed boarding time"] = "ticket transaction time; not confirmed boarding time"
    route_match_status: Literal["exact_label_candidate_unverified", "no_exact_label_candidate"]
    limitations: list[str]
