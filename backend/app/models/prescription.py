from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VehicleSwapExecution(Base):
    __tablename__ = "vehicle_swap_executions"
    __table_args__ = (
        Index("ix_vehicle_swap_executions_executed_at", "executed_at"),
        Index("ix_vehicle_swap_executions_terminal", "terminal_id", "executed_at"),
        {"schema": "audit"},
    )

    execution_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(String(150), nullable=False)
    terminal_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    executed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    group_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
