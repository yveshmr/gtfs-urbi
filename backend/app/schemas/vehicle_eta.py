from dataclasses import asdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.services.vehicle_eta_query import VehicleEtaResult


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
    calculation_mode: Literal["enriched", "planned_baseline"] = "enriched"
    vehicle_prefix: str
    trip_id: str
    route_id: str
    direction_id: int
    next_stop_id: str
    terminal_stop_id: str
    planned_trip_end_at: datetime | None = None
    remaining_segment_count: int
    current_time: EtaScenarioResponse
    future_time: EtaScenarioResponse


class VehicleEtaSnapshotResponse(VehicleEtaResponse):
    generated_at: datetime


class VehicleEtaSnapshotListResponse(BaseModel):
    generated_at: datetime | None
    count: int
    vehicles: list[VehicleEtaSnapshotResponse]


def build_vehicle_eta_response(
    result: VehicleEtaResult,
    *,
    queried_at: datetime,
    calculation_mode: Literal["enriched", "planned_baseline"] = "enriched",
) -> VehicleEtaResponse:
    return VehicleEtaResponse(
        queried_at=queried_at,
        calculation_mode=calculation_mode,
        vehicle_prefix=result.vehicle_prefix,
        trip_id=result.trip_id,
        route_id=result.route_id,
        direction_id=result.direction_id,
        next_stop_id=result.next_stop_id,
        terminal_stop_id=result.terminal_stop_id,
        planned_trip_end_at=result.planned_trip_end_at,
        remaining_segment_count=result.remaining_segment_count,
        current_time=EtaScenarioResponse(
            physical=EtaProjectionResponse(**asdict(result.current_time_physical)),
            service=EtaProjectionResponse(**asdict(result.current_time_service)),
        ),
        future_time=EtaScenarioResponse(
            physical=EtaProjectionResponse(**asdict(result.future_time_physical)),
            service=EtaProjectionResponse(**asdict(result.future_time_service)),
        ),
    )
