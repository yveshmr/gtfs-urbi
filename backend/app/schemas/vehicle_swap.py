from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SwapAssignmentResponse(BaseModel):
    commitment_vehicle_prefix: str
    assigned_vehicle_prefix: str
    departure_at: datetime
    assigned_vehicle_arrival_at: datetime
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


class TerminalSwapPlanResponse(BaseModel):
    terminal_id: str
    baseline_total_delay_seconds: int
    proposed_total_delay_seconds: int
    saved_delay_seconds: int
    baseline_delayed_trip_count: int
    proposed_delayed_trip_count: int
    baseline_max_delay_seconds: int
    proposed_max_delay_seconds: int
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
