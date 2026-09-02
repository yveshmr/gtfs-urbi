from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ProjectedVehiclePositionResponse(BaseModel):
    vehicle_prefix: str
    source_timestamp: datetime
    projected_at: datetime
    latitude: float
    longitude: float
    position_source: Literal["projected"] = "projected"
    gps_direction: float | None
    route_bearing_degrees: float | None
    speed_kmh: float | None
    low_speed_since: datetime | None
    current_line: str | None
    trip_id: str
    route_id: str
    route_short_name: str | None
    route_long_name: str | None
    headsign: str | None
    direction_id: int | None
    shape_id: str
    shape_position: float
    shape_progress_m: float
    distance_to_shape_m: float
    projection_quality: Literal["valid", "reduced"]
    correlation_level: int | None
    current_origin_stop_id: str | None
    current_origin_stop_name: str | None
    current_destination_stop_id: str | None
    current_destination_stop_name: str | None


class RawVehiclePositionResponse(BaseModel):
    vehicle_prefix: str
    source_timestamp: datetime
    latitude: float
    longitude: float
    position_source: Literal["gps"] = "gps"
    gps_direction: float | None
    speed_kmh: float | None
    current_line: str | None
    current_planned_time: str | None
    next_line: str | None
    next_trip_destination: str | None
    correlation_status: str | None
    correlation_reason: str | None
    map_match_status: str
    operational_class: Literal[
        "missing_planned_time",
        "ambiguous",
        "collecting",
        "no_exact_match",
        "other",
    ]


class ProjectedVehiclePositionListResponse(BaseModel):
    generated_at: datetime
    count: int
    monitored_count: int
    signal_window_seconds: int
    classification_counts: dict[str, int]
    vehicles: list[ProjectedVehiclePositionResponse]
    raw_vehicles: list[RawVehiclePositionResponse]


class SegmentSpeedMapItem(BaseModel):
    segment_id: str
    origin_stop_id: str
    origin_stop_name: str
    destination_stop_id: str
    destination_stop_name: str
    distance_m: float
    speed_kmh: float
    duration_seconds: float
    source: Literal["live", "historical", "gtfs_planned"]
    reliability: float
    sample_count: int
    window_start: datetime | None = None
    window_end: datetime | None = None
    historical_offset_minutes: int | None = None
    geometry: dict[str, Any]


class SegmentSpeedMapResponse(BaseModel):
    generated_at: datetime
    count: int
    source_counts: dict[str, int]
    segments: list[SegmentSpeedMapItem]


class TripStopGeometryResponse(BaseModel):
    stop_id: str
    stop_code: str | None
    stop_name: str
    stop_sequence: int
    latitude: float | None
    longitude: float | None
    shape_position: float | None
    shape_progress_m: float | None
    projection_quality: str | None
    arrival_seconds: int
    departure_seconds: int


class TripGeometryResponse(BaseModel):
    trip_id: str
    route_id: str
    route_short_name: str | None
    route_long_name: str | None
    route_color: str | None
    route_text_color: str | None
    headsign: str | None
    direction_id: int | None
    shape_id: str
    geometry: dict[str, Any]
    stops: list[TripStopGeometryResponse]
