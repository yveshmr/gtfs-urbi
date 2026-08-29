from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0003"
down_revision: str | None = "20260828_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gtfs_feeds",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("source_last_modified", sa.DateTime(timezone=True)),
        sa.Column("publisher_name", sa.String(255)),
        sa.Column("publisher_url", sa.Text()),
        sa.Column("language", sa.String(20)),
        sa.Column("feed_start_date", sa.Date()),
        sa.Column("feed_end_date", sa.Date()),
        sa.Column("feed_version", sa.String(100)),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
    )
    op.create_index(
        "ux_gtfs_feeds_content_hash", "gtfs_feeds", ["content_hash"], unique=True, schema="core"
    )
    op.create_index("ix_gtfs_feeds_retrieved_at", "gtfs_feeds", ["retrieved_at"], schema="core")

    op.create_table(
        "gtfs_agencies",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("agency_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("language", sa.String(20)),
        sa.Column("phone", sa.String(100)),
        sa.ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feed_id", "agency_id"),
        schema="core",
    )

    op.create_table(
        "gtfs_services",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(100), nullable=False),
        *[
            sa.Column(day, sa.Boolean(), nullable=False)
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        ],
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feed_id", "service_id"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_services_validity",
        "gtfs_services",
        ["feed_id", "start_date", "end_date"],
        schema="core",
    )

    op.create_table(
        "gtfs_routes",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.String(100), nullable=False),
        sa.Column("agency_id", sa.String(100)),
        sa.Column("short_name", sa.String(100)),
        sa.Column("long_name", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("route_type", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(6)),
        sa.Column("text_color", sa.String(6)),
        sa.ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["feed_id", "agency_id"], ["core.gtfs_agencies.feed_id", "core.gtfs_agencies.agency_id"]
        ),
        sa.PrimaryKeyConstraint("feed_id", "route_id"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_routes_short_name", "gtfs_routes", ["feed_id", "short_name"], schema="core"
    )

    op.create_table(
        "gtfs_service_exceptions",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(100), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("exception_type", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("exception_type IN (1, 2)", name="ck_gtfs_exception_type"),
        sa.ForeignKeyConstraint(
            ["feed_id", "service_id"],
            ["core.gtfs_services.feed_id", "core.gtfs_services.service_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feed_id", "service_id", "service_date"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_service_exceptions_date",
        "gtfs_service_exceptions",
        ["feed_id", "service_date"],
        schema="core",
    )

    op.create_table(
        "gtfs_shapes",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("shape_id", sa.String(100), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("LINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("point_count >= 2", name="ck_gtfs_shapes_point_count"),
        sa.ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feed_id", "shape_id"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_shapes_geometry",
        "gtfs_shapes",
        ["geometry"],
        postgresql_using="gist",
        schema="core",
    )

    op.create_table(
        "gtfs_shape_points",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("shape_id", sa.String(100), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("distance_traveled", sa.Float()),
        sa.Column(
            "location",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.CheckConstraint("sequence >= 0", name="ck_gtfs_shape_points_sequence"),
        sa.ForeignKeyConstraint(
            ["feed_id", "shape_id"],
            ["core.gtfs_shapes.feed_id", "core.gtfs_shapes.shape_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feed_id", "shape_id", "sequence"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_shape_points_location",
        "gtfs_shape_points",
        ["location"],
        postgresql_using="gist",
        schema="core",
    )

    op.create_table(
        "gtfs_stops",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("stop_id", sa.String(100), nullable=False),
        sa.Column("code", sa.String(100)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("zone_id", sa.String(100)),
        sa.Column("url", sa.Text()),
        sa.Column("location_type", sa.SmallInteger()),
        sa.Column("parent_station", sa.String(100)),
        sa.Column("location", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False)),
        sa.ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feed_id", "stop_id"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_stops_location", "gtfs_stops", ["location"], postgresql_using="gist", schema="core"
    )

    op.create_table(
        "gtfs_trips",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("trip_id", sa.String(150), nullable=False),
        sa.Column("route_id", sa.String(100), nullable=False),
        sa.Column("service_id", sa.String(100), nullable=False),
        sa.Column("headsign", sa.String(255)),
        sa.Column("direction_id", sa.SmallInteger()),
        sa.Column("block_id", sa.String(100)),
        sa.Column("shape_id", sa.String(100)),
        sa.ForeignKeyConstraint(["feed_id"], ["core.gtfs_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["feed_id", "route_id"], ["core.gtfs_routes.feed_id", "core.gtfs_routes.route_id"]
        ),
        sa.ForeignKeyConstraint(
            ["feed_id", "service_id"],
            ["core.gtfs_services.feed_id", "core.gtfs_services.service_id"],
        ),
        sa.ForeignKeyConstraint(
            ["feed_id", "shape_id"], ["core.gtfs_shapes.feed_id", "core.gtfs_shapes.shape_id"]
        ),
        sa.PrimaryKeyConstraint("feed_id", "trip_id"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_trips_correlation",
        "gtfs_trips",
        ["feed_id", "route_id", "direction_id"],
        schema="core",
    )
    op.create_index("ix_gtfs_trips_block_id", "gtfs_trips", ["feed_id", "block_id"], schema="core")

    op.create_table(
        "gtfs_stop_times",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("trip_id", sa.String(150), nullable=False),
        sa.Column("stop_sequence", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.String(100), nullable=False),
        sa.Column("arrival_seconds", sa.Integer(), nullable=False),
        sa.Column("departure_seconds", sa.Integer(), nullable=False),
        sa.Column("stop_headsign", sa.String(255)),
        sa.Column("pickup_type", sa.SmallInteger()),
        sa.Column("drop_off_type", sa.SmallInteger()),
        sa.Column("timepoint", sa.SmallInteger()),
        sa.CheckConstraint("arrival_seconds >= 0", name="ck_gtfs_stop_times_arrival"),
        sa.CheckConstraint("departure_seconds >= 0", name="ck_gtfs_stop_times_departure"),
        sa.CheckConstraint("stop_sequence >= 0", name="ck_gtfs_stop_times_sequence"),
        sa.ForeignKeyConstraint(
            ["feed_id", "trip_id"],
            ["core.gtfs_trips.feed_id", "core.gtfs_trips.trip_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feed_id", "stop_id"], ["core.gtfs_stops.feed_id", "core.gtfs_stops.stop_id"]
        ),
        sa.PrimaryKeyConstraint("feed_id", "trip_id", "stop_sequence"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_stop_times_stop", "gtfs_stop_times", ["feed_id", "stop_id"], schema="core"
    )
    op.create_index(
        "ix_gtfs_stop_times_trip_departure",
        "gtfs_stop_times",
        ["feed_id", "trip_id", "departure_seconds"],
        schema="core",
    )


def downgrade() -> None:
    for table_name in (
        "gtfs_stop_times",
        "gtfs_trips",
        "gtfs_stops",
        "gtfs_shape_points",
        "gtfs_shapes",
        "gtfs_service_exceptions",
        "gtfs_routes",
        "gtfs_services",
        "gtfs_agencies",
        "gtfs_feeds",
    ):
        op.drop_table(table_name, schema="core")
