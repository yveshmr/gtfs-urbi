from __future__ import annotations

import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GtfsFeed(Base):
    __tablename__ = "gtfs_feeds"
    __table_args__ = (
        Index("ux_gtfs_feeds_content_hash", "content_hash", unique=True),
        Index("ix_gtfs_feeds_retrieved_at", "retrieved_at"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    source_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publisher_name: Mapped[str | None] = mapped_column(String(255))
    publisher_url: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(20))
    feed_start_date: Mapped[date | None] = mapped_column(Date)
    feed_end_date: Mapped[date | None] = mapped_column(Date)
    feed_version: Mapped[str | None] = mapped_column(String(100))


class GtfsAgency(Base):
    __tablename__ = "gtfs_agencies"
    __table_args__ = (
        ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        PrimaryKeyConstraint("feed_id", "agency_id"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    agency_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(100))


class GtfsRoute(Base):
    __tablename__ = "gtfs_routes"
    __table_args__ = (
        ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["feed_id", "agency_id"],
            ["core.gtfs_agencies.feed_id", "core.gtfs_agencies.agency_id"],
        ),
        PrimaryKeyConstraint("feed_id", "route_id"),
        Index("ix_gtfs_routes_short_name", "feed_id", "short_name"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    route_id: Mapped[str] = mapped_column(String(100))
    agency_id: Mapped[str | None] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(100))
    long_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    route_type: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(String(6))
    text_color: Mapped[str | None] = mapped_column(String(6))


class GtfsService(Base):
    __tablename__ = "gtfs_services"
    __table_args__ = (
        ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        PrimaryKeyConstraint("feed_id", "service_id"),
        Index("ix_gtfs_services_validity", "feed_id", "start_date", "end_date"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    service_id: Mapped[str] = mapped_column(String(100))
    monday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tuesday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wednesday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thursday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    friday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saturday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sunday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class GtfsServiceException(Base):
    __tablename__ = "gtfs_service_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feed_id", "service_id"],
            ["core.gtfs_services.feed_id", "core.gtfs_services.service_id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("feed_id", "service_id", "service_date"),
        CheckConstraint("exception_type IN (1, 2)", name="ck_gtfs_exception_type"),
        Index("ix_gtfs_service_exceptions_date", "feed_id", "service_date"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    service_id: Mapped[str] = mapped_column(String(100))
    service_date: Mapped[date] = mapped_column(Date)
    exception_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class GtfsShape(Base):
    __tablename__ = "gtfs_shapes"
    __table_args__ = (
        ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        PrimaryKeyConstraint("feed_id", "shape_id"),
        CheckConstraint("point_count >= 2", name="ck_gtfs_shapes_point_count"),
        Index("ix_gtfs_shapes_geometry", "geometry", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    shape_id: Mapped[str] = mapped_column(String(100))
    geometry: Mapped[object] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=False),
        nullable=False,
    )
    point_count: Mapped[int] = mapped_column(Integer, nullable=False)


class GtfsShapePoint(Base):
    __tablename__ = "gtfs_shape_points"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feed_id", "shape_id"],
            ["core.gtfs_shapes.feed_id", "core.gtfs_shapes.shape_id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("feed_id", "shape_id", "sequence"),
        CheckConstraint("sequence >= 0", name="ck_gtfs_shape_points_sequence"),
        Index("ix_gtfs_shape_points_location", "location", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    shape_id: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column(Integer)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    distance_traveled: Mapped[float | None] = mapped_column(Float)
    location: Mapped[object] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=False,
    )


class GtfsShapeSegment(Base):
    __tablename__ = "gtfs_shape_segments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feed_id", "shape_id"],
            ["core.gtfs_shapes.feed_id", "core.gtfs_shapes.shape_id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("feed_id", "shape_id", "segment_sequence"),
        CheckConstraint("segment_sequence >= 0", name="ck_gtfs_shape_segments_sequence"),
        CheckConstraint("segment_length_m > 0", name="ck_gtfs_shape_segments_length"),
        CheckConstraint(
            "start_distance_m >= 0 AND end_distance_m > start_distance_m",
            name="ck_gtfs_shape_segments_distances",
        ),
        CheckConstraint(
            "start_fraction BETWEEN 0 AND 1 "
            "AND end_fraction BETWEEN 0 AND 1 "
            "AND end_fraction > start_fraction",
            name="ck_gtfs_shape_segments_fractions",
        ),
        Index("ix_gtfs_shape_segments_geometry", "geometry", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    shape_id: Mapped[str] = mapped_column(String(100))
    segment_sequence: Mapped[int] = mapped_column(Integer)
    geometry: Mapped[object] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=False),
        nullable=False,
    )
    segment_length_m: Mapped[float] = mapped_column(Float, nullable=False)
    start_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    end_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    start_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    end_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    bearing_degrees: Mapped[float] = mapped_column(Float, nullable=False)


class GtfsStop(Base):
    __tablename__ = "gtfs_stops"
    __table_args__ = (
        ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        PrimaryKeyConstraint("feed_id", "stop_id"),
        Index("ix_gtfs_stops_location", "location", postgresql_using="gist"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    stop_id: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    zone_id: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(Text)
    location_type: Mapped[int | None] = mapped_column(SmallInteger)
    parent_station: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[object | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )


class GtfsTrip(Base):
    __tablename__ = "gtfs_trips"
    __table_args__ = (
        ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["feed_id", "route_id"],
            ["core.gtfs_routes.feed_id", "core.gtfs_routes.route_id"],
        ),
        ForeignKeyConstraint(
            ["feed_id", "service_id"],
            ["core.gtfs_services.feed_id", "core.gtfs_services.service_id"],
        ),
        ForeignKeyConstraint(
            ["feed_id", "shape_id"],
            ["core.gtfs_shapes.feed_id", "core.gtfs_shapes.shape_id"],
        ),
        PrimaryKeyConstraint("feed_id", "trip_id"),
        CheckConstraint(
            "start_seconds IS NULL OR start_seconds >= 0",
            name="ck_gtfs_trips_start_seconds",
        ),
        Index(
            "ix_gtfs_trips_correlation",
            "feed_id",
            "route_id",
            "direction_id",
            "start_seconds",
        ),
        Index("ix_gtfs_trips_block_id", "feed_id", "block_id"),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    trip_id: Mapped[str] = mapped_column(String(150))
    route_id: Mapped[str] = mapped_column(String(100), nullable=False)
    service_id: Mapped[str] = mapped_column(String(100), nullable=False)
    headsign: Mapped[str | None] = mapped_column(String(255))
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    start_seconds: Mapped[int | None] = mapped_column(Integer)
    block_id: Mapped[str | None] = mapped_column(String(100))
    shape_id: Mapped[str | None] = mapped_column(String(100))


class GtfsStopTime(Base):
    __tablename__ = "gtfs_stop_times"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feed_id", "trip_id"],
            ["core.gtfs_trips.feed_id", "core.gtfs_trips.trip_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["feed_id", "stop_id"],
            ["core.gtfs_stops.feed_id", "core.gtfs_stops.stop_id"],
        ),
        PrimaryKeyConstraint("feed_id", "trip_id", "stop_sequence"),
        CheckConstraint("arrival_seconds >= 0", name="ck_gtfs_stop_times_arrival"),
        CheckConstraint("departure_seconds >= 0", name="ck_gtfs_stop_times_departure"),
        CheckConstraint("stop_sequence >= 0", name="ck_gtfs_stop_times_sequence"),
        Index("ix_gtfs_stop_times_stop", "feed_id", "stop_id"),
        Index("ix_gtfs_stop_times_trip_departure", "feed_id", "trip_id", "departure_seconds"),
        Index("ix_gtfs_stop_times_trip_shape_position", "feed_id", "trip_id", "shape_position"),
        Index("ix_gtfs_stop_times_trip_shape_progress", "feed_id", "trip_id", "shape_progress_m"),
        CheckConstraint(
            "shape_progress_m IS NULL OR shape_progress_m >= 0",
            name="ck_gtfs_stop_times_shape_progress",
        ),
        CheckConstraint(
            "shape_projection_quality IS NULL OR shape_projection_quality IN "
            "('valid', 'reduced', 'fallback_required')",
            name="ck_gtfs_stop_times_projection_quality",
        ),
        {"schema": "core"},
    )

    feed_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    trip_id: Mapped[str] = mapped_column(String(150))
    stop_sequence: Mapped[int] = mapped_column(Integer)
    stop_id: Mapped[str] = mapped_column(String(100), nullable=False)
    arrival_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_headsign: Mapped[str | None] = mapped_column(String(255))
    pickup_type: Mapped[int | None] = mapped_column(SmallInteger)
    drop_off_type: Mapped[int | None] = mapped_column(SmallInteger)
    timepoint: Mapped[int | None] = mapped_column(SmallInteger)
    shape_position: Mapped[float | None] = mapped_column(Float)
    shape_progress_m: Mapped[float | None] = mapped_column(Float)
    distance_to_shape_m: Mapped[float | None] = mapped_column(Float)
    shape_projection_quality: Mapped[str | None] = mapped_column(String(30))
