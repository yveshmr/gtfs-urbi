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


class ProjectedVehiclePositionListResponse(BaseModel):
    generated_at: datetime
    count: int
    vehicles: list[ProjectedVehiclePositionResponse]


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
