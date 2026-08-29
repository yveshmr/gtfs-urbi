from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name="ck_ingestion_runs_status",
        ),
        CheckConstraint(
            "records_received >= 0",
            name="ck_ingestion_runs_records_received",
        ),
        CheckConstraint(
            "records_written >= 0",
            name="ck_ingestion_runs_records_written",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_ingestion_runs_valid_period",
        ),
        Index(
            "ix_ingestion_runs_source_started_at",
            "source_system",
            "started_at",
        ),
        Index(
            "ix_ingestion_runs_status",
            "status",
        ),
        {"schema": "audit"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_system: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    resource_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    records_received: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    records_written: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    responses: Mapped[list[ApiResponse]] = relationship(
        back_populates="run",
    )


class ApiResponse(Base):
    __tablename__ = "api_responses"
    __table_args__ = (
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_api_responses_duration_ms",
        ),
        CheckConstraint(
            "http_status BETWEEN 100 AND 599",
            name="ck_api_responses_http_status",
        ),
        Index(
            "ix_api_responses_run_id",
            "ingestion_run_id",
        ),
        Index(
            "ix_api_responses_received_at",
            "received_at",
        ),
        Index(
            "ix_api_responses_payload_hash",
            "payload_hash",
        ),
        {"schema": "raw"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "audit.ingestion_runs.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    endpoint_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    source_model: Mapped[str | None] = mapped_column(String(50))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    request_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    payload: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run: Mapped[IngestionRun] = relationship(
        back_populates="responses",
    )
