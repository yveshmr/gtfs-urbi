from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VehicleSwapDecision(Base):
    __tablename__ = "vehicle_swap_decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_analysis', 'claimed', 'executed', 'rejected')",
            name="ck_vehicle_swap_decisions_status",
        ),
        Index("ix_vehicle_swap_decisions_updated_at", "updated_at"),
        Index("ix_vehicle_swap_decisions_terminal", "terminal_id", "updated_at"),
        {"schema": "audit"},
    )

    execution_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(String(150), nullable=False)
    terminal_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    group_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class VehicleSwapDecisionEvent(Base):
    __tablename__ = "vehicle_swap_decision_events"
    __table_args__ = (
        Index("ix_vehicle_swap_decision_events_key", "execution_key", "occurred_at"),
        {"schema": "audit"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    execution_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("audit.vehicle_swap_decisions.execution_key", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
