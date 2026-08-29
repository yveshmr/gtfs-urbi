from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EtaTargetResponse(BaseModel):
    value_seconds: float | None
    estimated_at: datetime | None
    reliability: float
    segments_covered: int
    segments_total: int
    source_counts: dict[str, int]
    complete: bool
    missing_origin_stop_id: str | None
    missing_destination_stop_id: str | None


class EtaProjectionResponse(BaseModel):
    scope: Literal["physical", "service"]
    scenario: Literal["current_time", "future_time"]
    next_stop: EtaTargetResponse
    trip_end: EtaTargetResponse


class EtaScenarioResponse(BaseModel):
    physical: EtaProjectionResponse
    service: EtaProjectionResponse


class VehicleEtaResponse(BaseModel):
    queried_at: datetime
    vehicle_prefix: str
    trip_id: str
    route_id: str
    direction_id: int
    next_stop_id: str
    terminal_stop_id: str
    remaining_segment_count: int
    current_time: EtaScenarioResponse
    future_time: EtaScenarioResponse
