from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VehicleCurrentState(Base):
    __tablename__ = "vehicle_current_states"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_vehicle_current_states_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_vehicle_current_states_longitude",
        ),
        CheckConstraint(
            "speed_kmh IS NULL OR speed_kmh >= 0",
            name="ck_vehicle_current_states_speed",
        ),
        CheckConstraint(
            "shape_position IS NULL OR shape_position BETWEEN 0 AND 1",
            name="ck_vehicle_current_states_shape_position",
        ),
        CheckConstraint(
            "distance_to_shape_m IS NULL OR distance_to_shape_m >= 0",
            name="ck_vehicle_current_states_shape_distance",
        ),
        CheckConstraint(
            "shape_progress_m IS NULL OR shape_progress_m >= 0",
            name="ck_vehicle_current_states_shape_progress",
        ),
        CheckConstraint(
            "projection_quality IS NULL OR projection_quality IN "
            "('valid', 'reduced', 'fallback_required')",
            name="ck_vehicle_current_states_projection_quality",
        ),
        CheckConstraint(
            "last_boundary_projection_quality IS NULL OR "
            "last_boundary_projection_quality IN "
            "('valid', 'reduced', 'fallback_required')",
            name="ck_vehicle_current_states_boundary_projection_quality",
        ),
        CheckConstraint(
            "position_sample_count BETWEEN 1 AND 3",
            name="ck_vehicle_current_states_sample_count",
        ),
        CheckConstraint(
            "map_match_status IN ('collecting', 'resolved', 'ambiguous', 'fallback_required')",
            name="ck_vehicle_current_states_map_match_status",
        ),
        Index("ix_vehicle_current_states_source_timestamp", "source_timestamp"),
        Index("ix_vehicle_current_states_current_line", "normalized_current_line"),
        Index("ix_vehicle_current_states_location", "location", postgresql_using="gist"),
        Index("ix_vehicle_current_states_trip", "feed_id", "trip_id"),
        Index("ix_vehicle_current_states_correlation_status", "correlation_status"),
        ForeignKeyConstraint(
            ["feed_id", "trip_id"],
            ["core.gtfs_trips.feed_id", "core.gtfs_trips.trip_id"],
            ondelete="RESTRICT",
        ),
        {"schema": "realtime"},
    )

    vehicle_prefix: Mapped[str] = mapped_column(String(50), primary_key=True)
    imei: Mapped[str | None] = mapped_column(String(50))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location: Mapped[object | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    gps_direction: Mapped[float | None] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)

    current_line: Mapped[str | None] = mapped_column(String(100))
    normalized_current_line: Mapped[str | None] = mapped_column(String(100))
    current_planned_time: Mapped[str | None] = mapped_column(String(100))
    current_direction: Mapped[str | None] = mapped_column(String(20))
    current_schedule_position: Mapped[str | None] = mapped_column(Text)
    current_actual_time: Mapped[str | None] = mapped_column(String(100))

    next_planned_time: Mapped[str | None] = mapped_column(String(100))
    next_trip_point: Mapped[str | None] = mapped_column(Text)
    next_schedule_position: Mapped[str | None] = mapped_column(Text)
    next_line: Mapped[str | None] = mapped_column(String(100))
    next_direction: Mapped[str | None] = mapped_column(String(20))
    next_trip_destination: Mapped[str | None] = mapped_column(Text)

    feed_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    trip_id: Mapped[str | None] = mapped_column(String(150))
    route_id: Mapped[str | None] = mapped_column(String(100))
    shape_id: Mapped[str | None] = mapped_column(String(100))
    correlation_status: Mapped[str | None] = mapped_column(String(30))
    correlation_reason: Mapped[str | None] = mapped_column(String(50))
    correlation_level: Mapped[int | None] = mapped_column(Integer)
    correlation_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shape_position: Mapped[float | None] = mapped_column(Float)
    shape_progress_m: Mapped[float | None] = mapped_column(Float)
    distance_to_shape_m: Mapped[float | None] = mapped_column(Float)
    projected_location: Mapped[object | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    projected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    projection_quality: Mapped[str | None] = mapped_column(String(30))
    current_origin_stop_id: Mapped[str | None] = mapped_column(String(100))
    current_destination_stop_id: Mapped[str | None] = mapped_column(String(100))
    current_origin_stop_sequence: Mapped[int | None] = mapped_column(Integer)
    current_destination_stop_sequence: Mapped[int | None] = mapped_column(Integer)
    previous_state_1: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    previous_state_2: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    position_sample_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    map_match_status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_boundary_stop_id: Mapped[str | None] = mapped_column(String(100))
    last_boundary_stop_sequence: Mapped[int | None] = mapped_column(Integer)
    last_boundary_progress_m: Mapped[float | None] = mapped_column(Float)
    last_boundary_projection_quality: Mapped[str | None] = mapped_column(String(30))
    last_boundary_crossed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_boundary_observation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
