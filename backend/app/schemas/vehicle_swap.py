from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SwapAssignmentResponse(BaseModel):
    commitment_vehicle_prefix: str
    assigned_vehicle_prefix: str
    departure_at: datetime
    commitment_vehicle_arrival_at: datetime
    assigned_vehicle_arrival_at: datetime
    assigned_arrival_margin_seconds: int
    next_line: str | None
    next_direction: str | None
    next_destination: str | None
    next_schedule_position: str | None
    baseline_delay_seconds: int
    proposed_delay_seconds: int
    delay_reduction_seconds: int
    eta_reliability: float
    eta_source_counts: dict[str, int]
    protected: bool
    changed: bool


class ExchangeGroupResponse(BaseModel):
    execution_key: str
    group_id: str
    terminal_id: str
    vehicle_prefixes: list[str]
    vehicle_count: int
    baseline_total_delay_seconds: int
    proposed_total_delay_seconds: int
    saved_delay_seconds: int
    baseline_max_delay_seconds: int
    proposed_max_delay_seconds: int
    minimum_eta_reliability: float
    steps: list[SwapAssignmentResponse]


class TerminalSwapPlanResponse(BaseModel):
    terminal_id: str
    baseline_total_delay_seconds: int
    proposed_total_delay_seconds: int
    saved_delay_seconds: int
    baseline_delayed_trip_count: int
    proposed_delayed_trip_count: int
    baseline_max_delay_seconds: int
    proposed_max_delay_seconds: int
    exchange_groups: list[ExchangeGroupResponse]
    assignments: list[SwapAssignmentResponse]


class VehicleSwapPrescriptionResponse(BaseModel):
    status: Literal["ready", "no_data", "stale"]
    evaluated_at: datetime
    snapshot_generated_at: datetime | None
    snapshot_age_seconds: float | None
    delay_threshold_minutes: int
    protected_window_minutes: int
    eligible_vehicle_count: int
    terminal_count: int
    plan_count: int
    total_saved_delay_seconds: int
    plans: list[TerminalSwapPlanResponse]


class ExecuteExchangeGroupRequest(BaseModel):
    execution_key: str = Field(min_length=64, max_length=64)
    executed_by: str = Field(min_length=1, max_length=100)


class SwapExecutionResponse(BaseModel):
    execution_key: str
    group_id: str
    terminal_id: str
    snapshot_generated_at: datetime
    executed_at: datetime
    executed_by: str


class SwapExecutionListResponse(BaseModel):
    count: int
    executions: list[SwapExecutionResponse]
