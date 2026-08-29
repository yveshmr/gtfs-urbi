from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0004"
down_revision: str | None = "20260828_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gtfs_trips",
        sa.Column("start_seconds", sa.Integer()),
        schema="core",
    )
    op.execute(
        """
        UPDATE core.gtfs_trips AS trip
        SET start_seconds = first_stop.departure_seconds
        FROM (
            SELECT DISTINCT ON (feed_id, trip_id)
                feed_id,
                trip_id,
                departure_seconds
            FROM core.gtfs_stop_times
            ORDER BY feed_id, trip_id, stop_sequence
        ) AS first_stop
        WHERE trip.feed_id = first_stop.feed_id
          AND trip.trip_id = first_stop.trip_id
        """
    )
    op.create_check_constraint(
        "ck_gtfs_trips_start_seconds",
        "gtfs_trips",
        "start_seconds IS NULL OR start_seconds >= 0",
        schema="core",
    )
    op.drop_index(
        "ix_gtfs_trips_correlation",
        table_name="gtfs_trips",
        schema="core",
    )
    op.create_index(
        "ix_gtfs_trips_correlation",
        "gtfs_trips",
        ["feed_id", "route_id", "direction_id", "start_seconds"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gtfs_trips_correlation",
        table_name="gtfs_trips",
        schema="core",
    )
    op.create_index(
        "ix_gtfs_trips_correlation",
        "gtfs_trips",
        ["feed_id", "route_id", "direction_id"],
        schema="core",
    )
    op.drop_constraint(
        "ck_gtfs_trips_start_seconds",
        "gtfs_trips",
        schema="core",
        type_="check",
    )
    op.drop_column("gtfs_trips", "start_seconds", schema="core")
