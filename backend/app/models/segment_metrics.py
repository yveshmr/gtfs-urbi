from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SegmentCompletionObservation(Base):
    __tablename__ = "segment_completion_observations"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_completion_observations_scope",
        ),
        CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_completion_observations_dimensions",
        ),
        CheckConstraint(
            "duration_seconds > 0 AND distance_m > 0 AND average_speed_kmh > 0",
            name="ck_segment_completion_observations_measurements",
        ),
        CheckConstraint(
            "confidence IN ('high', 'reduced')",
            name="ck_segment_completion_observations_confidence",
        ),
        CheckConstraint(
            "(accepted AND weight > 0 AND weight <= 1 AND rejection_reason IS NULL) "
            "OR (NOT accepted AND weight = 0 AND rejection_reason IS NOT NULL)",
            name="ck_segment_completion_observations_assessment",
        ),
        CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('speed_over_80', 'mad_outlier', 'invalid_measurement')",
            name="ck_segment_completion_observations_rejection_reason",
        ),
        CheckConstraint(
            "expires_at = completed_at + INTERVAL '1 hour'",
            name="ck_segment_completion_observations_retention",
        ),
        Index(
            "ix_segment_completion_observations_metric_completed",
            "metric_key",
            "completed_at",
        ),
        Index("ix_segment_completion_observations_expires_at", "expires_at"),
        {"schema": "analytics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    route_id: Mapped[str | None] = mapped_column(String(100))
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    source_feed_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.gtfs_feeds.id", ondelete="CASCADE"),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    average_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SegmentLiveMetric5m(Base):
    __tablename__ = "segment_live_metrics_5m"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_live_metrics_5m_scope",
        ),
        CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_live_metrics_5m_dimensions",
        ),
        CheckConstraint(
            "window_end = window_start + INTERVAL '5 minutes'",
            name="ck_segment_live_metrics_5m_window",
        ),
        CheckConstraint(
            "sample_count_total = sample_count_accepted + sample_count_rejected",
            name="ck_segment_live_metrics_5m_sample_counts",
        ),
        CheckConstraint(
            "sample_count_total > 0",
            name="ck_segment_live_metrics_5m_has_samples",
        ),
        CheckConstraint(
            "accepted_weight >= 0",
            name="ck_segment_live_metrics_5m_accepted_weight",
        ),
        CheckConstraint(
            "reliability BETWEEN 0 AND 1",
            name="ck_segment_live_metrics_5m_reliability",
        ),
        CheckConstraint(
            "status IN ('insufficient', 'low', 'medium', 'high', 'anomalous')",
            name="ck_segment_live_metrics_5m_status",
        ),
        Index(
            "ix_segment_live_metrics_5m_stops",
            "origin_stop_id",
            "destination_stop_id",
        ),
        Index(
            "ix_segment_live_metrics_5m_service",
            "route_id",
            "direction_id",
        ),
        Index("ix_segment_live_metrics_5m_window_start", "window_start"),
        {"schema": "analytics"},
    )

    metric_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    route_id: Mapped[str | None] = mapped_column(String(100))
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    source_feed_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.gtfs_feeds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_count_total: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_weight: Mapped[float] = mapped_column(Float, nullable=False)
    mean_seconds: Mapped[float | None] = mapped_column(Float)
    median_seconds: Mapped[float | None] = mapped_column(Float)
    standard_deviation_seconds: Mapped[float | None] = mapped_column(Float)
    minimum_seconds: Mapped[float | None] = mapped_column(Float)
    maximum_seconds: Mapped[float | None] = mapped_column(Float)
    reliability: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SegmentDailyMetric5m(Base):
    __tablename__ = "segment_daily_metrics_5m"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_daily_metrics_5m_scope",
        ),
        CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_daily_metrics_5m_dimensions",
        ),
        CheckConstraint(
            "day_type IN ('weekday', 'saturday', 'sunday')",
            name="ck_segment_daily_metrics_5m_day_type",
        ),
        CheckConstraint(
            "slot_index BETWEEN 0 AND 287",
            name="ck_segment_daily_metrics_5m_slot",
        ),
        CheckConstraint(
            "sample_count_total = sample_count_accepted + sample_count_rejected",
            name="ck_segment_daily_metrics_5m_sample_counts",
        ),
        CheckConstraint(
            "sample_count_total > 0 AND accepted_weight >= 0",
            name="ck_segment_daily_metrics_5m_samples",
        ),
        CheckConstraint(
            "reliability BETWEEN 0 AND 1",
            name="ck_segment_daily_metrics_5m_reliability",
        ),
        PrimaryKeyConstraint("metric_key", "service_date", "slot_index"),
        Index(
            "ix_segment_daily_metrics_5m_lookup",
            "day_type",
            "slot_index",
            "service_date",
        ),
        Index("ix_segment_daily_metrics_5m_service_date", "service_date"),
        {"schema": "analytics"},
    )

    metric_key: Mapped[str] = mapped_column(String(64))
    service_date: Mapped[date] = mapped_column(Date)
    slot_index: Mapped[int] = mapped_column(SmallInteger)
    day_type: Mapped[str] = mapped_column(String(10), nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    route_id: Mapped[str | None] = mapped_column(String(100))
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    source_feed_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.gtfs_feeds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sample_count_total: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_weight: Mapped[float] = mapped_column(Float, nullable=False)
    mean_seconds: Mapped[float | None] = mapped_column(Float)
    median_seconds: Mapped[float | None] = mapped_column(Float)
    standard_deviation_seconds: Mapped[float | None] = mapped_column(Float)
    minimum_seconds: Mapped[float | None] = mapped_column(Float)
    maximum_seconds: Mapped[float | None] = mapped_column(Float)
    m2_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    reliability: Mapped[float] = mapped_column(Float, nullable=False)
    last_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SegmentProfile5m(Base):
    __tablename__ = "segment_profiles_5m"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_profiles_5m_scope",
        ),
        CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_profiles_5m_dimensions",
        ),
        CheckConstraint(
            "day_type IN ('weekday', 'saturday', 'sunday')",
            name="ck_segment_profiles_5m_day_type",
        ),
        CheckConstraint(
            "slot_index BETWEEN 0 AND 287",
            name="ck_segment_profiles_5m_slot",
        ),
        CheckConstraint(
            "sample_count_total = sample_count_accepted + sample_count_rejected",
            name="ck_segment_profiles_5m_sample_counts",
        ),
        CheckConstraint(
            "sample_count_total >= 0",
            name="ck_segment_profiles_5m_nonnegative_samples",
        ),
        CheckConstraint(
            "accepted_weight >= 0",
            name="ck_segment_profiles_5m_accepted_weight",
        ),
        CheckConstraint(
            "reliability BETWEEN 0 AND 1",
            name="ck_segment_profiles_5m_reliability",
        ),
        CheckConstraint(
            "reference_end_date = reference_start_date + 6",
            name="ck_segment_profiles_5m_reference_period",
        ),
        PrimaryKeyConstraint("metric_key", "day_type", "slot_index"),
        Index(
            "ix_segment_profiles_5m_stops",
            "origin_stop_id",
            "destination_stop_id",
        ),
        Index(
            "ix_segment_profiles_5m_service",
            "route_id",
            "direction_id",
        ),
        {"schema": "analytics"},
    )

    metric_key: Mapped[str] = mapped_column(String(64))
    day_type: Mapped[str] = mapped_column(String(10))
    slot_index: Mapped[int] = mapped_column(SmallInteger)
    reference_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    route_id: Mapped[str | None] = mapped_column(String(100))
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    last_source_feed_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.gtfs_feeds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sample_count_total: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_weight: Mapped[float] = mapped_column(Float, nullable=False)
    mean_seconds: Mapped[float | None] = mapped_column(Float)
    m2_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    standard_deviation_seconds: Mapped[float | None] = mapped_column(Float)
    median_seconds: Mapped[float | None] = mapped_column(Float)
    mad_seconds: Mapped[float | None] = mapped_column(Float)
    ewma_seconds: Mapped[float | None] = mapped_column(Float)
    minimum_seconds: Mapped[float | None] = mapped_column(Float)
    maximum_seconds: Mapped[float | None] = mapped_column(Float)
    reliability: Mapped[float] = mapped_column(Float, nullable=False)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SegmentProfileRefreshState(Base):
    __tablename__ = "segment_profile_refresh_state"
    __table_args__ = (
        CheckConstraint(
            "reference_end_date = reference_start_date + 6",
            name="ck_segment_profile_refresh_state_period",
        ),
        {"schema": "analytics"},
    )

    profile_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    reference_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
