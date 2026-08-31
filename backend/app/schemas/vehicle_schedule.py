from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VehicleScheduleContextResponse(BaseModel):
    vehicle_prefix: str
    planned_start_at: datetime | None
    actual_start_at: datetime | None
    planned_end_at: datetime | None
    actual_end_at: datetime | None
    origin_name: str | None
    destination_name: str | None
    attendance_code: str | None
    activity: str | None
    schedule_table: str | None
    line: str | None
    direction: str | None
    day_type: str | None
    trip_number: str | None


class VehicleScheduleContextListResponse(BaseModel):
    status: Literal["ready", "stale"]
    generated_at: datetime
    cache_age_seconds: float
    count: int
    vehicles: list[VehicleScheduleContextResponse]
