from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]


class OperationalHealthResponse(BaseModel):
    status: Literal["operational", "degraded", "starting"]
    source: Literal["cittati"] = "cittati"
    latest_attempt_status: str | None
    last_success_at: datetime | None
    last_success_age_seconds: float | None
