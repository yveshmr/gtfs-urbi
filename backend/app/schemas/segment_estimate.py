from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SegmentEstimateValue(BaseModel):
    value_seconds: float | None
    reliability: float
    sample_count: int
    source: Literal["live", "historical", "gtfs_planned", "unavailable"]
    age_seconds: float | None
    historical_offset_minutes: int | None


class SegmentEstimateResponse(BaseModel):
    queried_at: datetime
    origin_stop_id: str
    destination_stop_id: str
    route_id: str | None
    direction_id: int | None
    physical: SegmentEstimateValue
    service: SegmentEstimateValue | None
