from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    processed_data_available: bool
    gtfs_available: bool
    gtfs_processed_available: bool
    generated_at: datetime


class ReadinessResponse(BaseModel):
    status: str
    processed_data_available: bool
    generated_at: datetime


class SystemCapabilitiesResponse(BaseModel):
    generated_at: datetime
    historical_ticket_analytics: bool
    gtfs_stop_catalog: bool
    gtfs_map_coordinates: bool
    scheduled_journey_search: bool
    trip_level_load_estimation: bool
    crowd_classification: bool
    live_vehicle_positions: bool
    live_vehicle_feed_configured: bool = False
    community_reporting: bool = True
    opt_in_presence: bool = False
    historical_ticket_activity_forecast: bool = True
    explanation: list[str]


class DatasetCatalogEntry(BaseModel):
    dataset_name: str
    status: str
    source_file: str | None = None
    source_sha256: str | None = None
    source_size_bytes: int | None = None
    generated_at: datetime | None = None
    schema_version: str | None = None
    pipeline_version: str | None = None
    input_rows: int | None = None
    retained_rows: int | None = None
    excluded_rows: int | None = None
    first_observed: datetime | date | None = None
    last_observed: datetime | date | None = None


class DatasetCatalogResponse(BaseModel):
    generated_at: datetime
    datasets: list[DatasetCatalogEntry]


class MethodologyResponse(BaseModel):
    generated_at: datetime
    historical_demand: str
    segment_load: str
    crowd_categories: str
    journey_routing: str
    confidence: str


class RouteCatalogItem(BaseModel):
    route_label: str
    passenger_volume: int
    transaction_count: int
    start_label_count: int
    first_observed_date: date
    last_observed_date: date


class RouteListResponse(BaseModel):
    data_source: str
    generated_at: datetime
    data_status: Literal["historical"] = "historical"
    measure: Literal["recorded_ticket_volume_by_route_label"] = "recorded_ticket_volume_by_route_label"
    items: list[RouteCatalogItem]
    limit: int
    offset: int
    next_offset: int | None = None


class RouteHourProfile(BaseModel):
    transaction_hour: int
    passenger_volume: int
    transaction_count: int
    observed_dates: int


class RouteWeekdayProfile(BaseModel):
    day_of_week: int
    passenger_volume: int
    transaction_count: int
    observed_dates: int


class RouteProfileResponse(BaseModel):
    data_source: str
    generated_at: datetime
    data_status: Literal["historical"] = "historical"
    route_label: str
    first_observed_date: date | None
    last_observed_date: date | None
    passenger_volume: int
    transaction_count: int
    start_label_count: int
    time_basis: str = "created_at transaction time"
    hourly_profile: list[RouteHourProfile]
    weekday_profile: list[RouteWeekdayProfile]


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class StopListItem(BaseModel):
    id: str
    stop_name: str
    coordinates: Coordinates | None = None
    demand_available: bool = False


class StopListResponse(BaseModel):
    items: list[StopListItem]
    source: str
    total_returned: int
    offset: int = 0
    next_offset: int | None = None


class StopMapResponse(BaseModel):
    items: list[StopListItem]
    source: str
    total_returned: int
    next_offset: int | None = None


class StopDemandObservation(BaseModel):
    date: date
    route: str | None
    day_of_week: int
    transaction_hour: int
    passenger_volume: int
    transaction_count: int


class StopDemandResponse(BaseModel):
    stop_name: str
    stop_id: str
    passenger_volume: int
    transaction_count: int
    prediction_type: str = "historical_ticket_start_volume"
    timestamp_basis: str = "ticket transaction time; not verified boarding time"
    status: str = "historical"
    data_source: str
    generated_at: datetime
    days_covered: int
    observation_count: int
    observations_truncated: bool
    total_observations: int = 0
    next_offset: int | None = None
    confidence: str
    confidence_note: str
    observations: list[StopDemandObservation]


class StopDetailResponse(BaseModel):
    id: str
    stop_name: str
    coordinates: Coordinates | None = None
    data_source: str
    data_status: Literal["historical"] = "historical"
    first_observed_date: date | None
    last_observed_date: date | None
    passenger_volume: int
    transaction_count: int
    routes_observed: int


class OverviewResponse(BaseModel):
    dataset_rows: int
    retained_rows: int
    excluded_rows: int
    dataset_min_timestamp: datetime
    dataset_max_timestamp: datetime
    generated_at: datetime
    distinct_routes: int
    distinct_vehicles: int
    distinct_start_stops: int
    distinct_end_stops: int
    null_vehicle_rows: int
    invalid_passenger_rows: int
    exact_duplicate_rows: int
    passenger_volume_total: int
    passenger_count_mean: float
    null_start_stop_rows: int
    null_end_stop_rows: int
    null_route_rows: int
    data_source: str
    data_status: Literal["historical"] = "historical"
    prediction_type: Literal["data_quality_overview"] = "data_quality_overview"
    occupancy_predictions: Literal["unavailable"] = "unavailable"
    caveat: str


class AnalyticsPoint(BaseModel):
    period: str
    passenger_volume: int
    transaction_count: int


class AnalyticsSeriesResponse(BaseModel):
    data_source: str
    data_status: Literal["historical"] = "historical"
    measure: Literal["recorded_ticket_volume"] = "recorded_ticket_volume"
    time_basis: str = "created_at transaction time"
    generated_at: datetime
    points: list[AnalyticsPoint]


class PeakHourItem(BaseModel):
    transaction_hour: int
    passenger_volume: int
    transaction_count: int
    observed_dates: int


class PeakHoursResponse(BaseModel):
    data_source: str
    data_status: Literal["historical"] = "historical"
    day_type: Literal["all", "weekday", "weekend"]
    time_basis: str = "created_at transaction time"
    generated_at: datetime
    hours: list[PeakHourItem]


class RouteSummary(BaseModel):
    route: str
    passenger_volume: int
    transaction_count: int
    stop_labels: int


class CorridorResponse(BaseModel):
    data_source: str
    data_status: Literal["historical"] = "historical"
    measure: Literal["recorded_ticket_volume_by_route_label"] = "recorded_ticket_volume_by_route_label"
    generated_at: datetime
    routes: list[RouteSummary]


class ServiceProfileItem(BaseModel):
    is_ac: bool | None
    ticket_type_id: int | None
    passenger_volume: int
    transaction_count: int
    observed_dates: int


class ServiceProfileResponse(BaseModel):
    data_source: str
    data_status: Literal["historical"] = "historical"
    generated_at: datetime
    time_basis: str = "created_at transaction time"
    semantic_caveat: str
    groups: list[ServiceProfileItem]


class JourneySearchRequest(BaseModel):
    origin_stop_id: str
    destination_stop_id: str
    departure_datetime: datetime
    preference: Literal["fastest", "balanced", "comfort"] = "balanced"
    max_transfers: int = Field(default=1, ge=0, le=3)


class JourneyStop(BaseModel):
    stop_id: str
    stop_name: str


class JourneyLegResponse(BaseModel):
    trip_id: str
    route_id: str
    route_name: str
    from_stop: JourneyStop
    to_stop: JourneyStop
    departure_datetime: datetime
    arrival_datetime: datetime
    stop_sequence: list[str]


class JourneyOptionResponse(BaseModel):
    legs: list[JourneyLegResponse]
    departure_datetime: datetime
    arrival_datetime: datetime
    duration_seconds: int
    waiting_seconds: int
    transfers: int
    transfer_stops: list[str]
    eta_source: str
    crowd_status: Literal["unavailable"] = "unavailable"
    score: float
    score_components: dict[str, float | None]


class JourneySearchResponse(BaseModel):
    options: list[JourneyOptionResponse]
    origin_stop_id: str
    destination_stop_id: str
    preference: Literal["fastest", "balanced", "comfort"]
    data_source: str
    data_status: Literal["scheduled", "unavailable"]
    generated_at: datetime
    crowd_data_available: Literal[False] = False
    ranking_note: str
    walking_connections_available: Literal[False] = False
    message: str | None = None


class CrowdReportRequest(BaseModel):
    stop_id: str = Field(min_length=1, max_length=128)
    category: Literal["low", "moderate", "high", "very_high"]
    observed_at: datetime
    route_id: str | None = Field(default=None, max_length=128)
    feedback_code: Literal["long_wait", "bus_arriving", "service_disruption", "other"] | None = None


class CrowdReportResponse(BaseModel):
    report_id: str
    stop_id: str
    stop_name: str
    category: Literal["low", "moderate", "high", "very_high"]
    observed_at: datetime
    created_at: datetime
    expires_at: datetime
    status: Literal["COMMUNITY_REPORTED"] = "COMMUNITY_REPORTED"
    observation_type: Literal["subjective_category_not_headcount"] = "subjective_category_not_headcount"
    stop_identity_status: str


class CommunityReportItem(BaseModel):
    report_id: str
    stop_id: str
    stop_name: str
    route_id: str | None
    category: Literal["low", "moderate", "high", "very_high"]
    feedback_code: str | None
    observed_at: datetime
    created_at: datetime
    expires_at: datetime


class CommunityReportsResponse(BaseModel):
    stop_id: str
    status: Literal["COMMUNITY_REPORTED", "UNAVAILABLE"]
    source: Literal["community_reports"] = "community_reports"
    report_count: int
    reports: list[CommunityReportItem]
    generated_at: datetime
    limitations: list[str]


class CommunityCrowdResponse(BaseModel):
    stop_id: str
    stop_name: str
    status: Literal["COMMUNITY_REPORTED", "UNAVAILABLE"]
    observation_type: Literal["community_category_aggregate"] = "community_category_aggregate"
    crowd_category: Literal["low", "moderate", "high", "very_high"] | None
    report_count: int
    agreement_fraction: float | None
    evidence_quality: Literal["limited_community_sample", "insufficient_reports"]
    generated_at: datetime
    freshness_seconds: int | None
    limitations: list[str]


class PresenceSignalRequest(BaseModel):
    stop_id: str = Field(min_length=1, max_length=128)
    consent: Literal[True]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float = Field(gt=0, le=1000)


class PresenceSignalResponse(BaseModel):
    signal_id: str
    stop_id: str
    created_at: datetime
    expires_at: datetime
    status: Literal["ACCEPTED"]
    storage_note: str


class PresenceAggregateResponse(BaseModel):
    stop_id: str
    status: Literal["COMMUNITY_REPORTED", "UNAVAILABLE"]
    signal_count: int
    measure: Literal["active_opt_in_participating_signals"] = "active_opt_in_participating_signals"
    generated_at: datetime
    expires_after_seconds: int
    limitations: list[str]


class RealtimeStatusResponse(BaseModel):
    status: Literal["UNAVAILABLE", "HEALTHY", "STALE", "ERROR"]
    configured: bool
    authorized: bool
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    feed_timestamp: datetime | None
    current_vehicle_count: int
    stale_vehicle_count: int
    last_error_code: str | None
    generated_at: datetime
    data_source: str


class VehiclePositionResponse(BaseModel):
    vehicle_id: str
    trip_id: str | None
    route_id: str | None
    latitude: float
    longitude: float
    bearing: float | None
    speed_meters_per_second: float | None
    current_stop_id: str | None
    current_stop_sequence: int | None
    current_status: str | None
    position_timestamp: datetime
    feed_timestamp: datetime | None
    freshness_seconds: int
    status: Literal["LIVE_OBSERVED"] = "LIVE_OBSERVED"
    data_source: str


class VehicleListResponse(BaseModel):
    status: Literal["HEALTHY", "STALE", "UNAVAILABLE", "ERROR"]
    generated_at: datetime
    last_success_at: datetime | None
    vehicles: list[VehiclePositionResponse]
    data_source: str


class TicketActivityForecastResponse(BaseModel):
    stop_id: str
    target_date: date
    target_hour: int
    status: Literal["PREDICTED", "UNAVAILABLE", "STALE"]
    prediction_type: Literal["ticket_transaction_activity_proxy"] = "ticket_transaction_activity_proxy"
    predicted_passenger_ticket_volume: float | None
    predicted_transaction_count: float | None
    comparable_days: int
    historical_range_passenger_volume: tuple[int, int] | None
    historical_max_date: date | None
    method: str
    data_source: str
    generated_at: datetime
    evidence_quality: str
    limitations: list[str]

