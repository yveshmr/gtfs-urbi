from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0009"
down_revision: str | None = "20260828_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROJECT_STOP_TIMES_SQL = """
UPDATE core.gtfs_stop_times AS stop_time
SET
    shape_position = ST_LineLocatePoint(shape.geometry, stop.location),
    distance_to_shape_m = ST_Distance(
        stop.location::geography,
        ST_ClosestPoint(shape.geometry, stop.location)::geography
    )
FROM core.gtfs_trips AS trip
JOIN core.gtfs_shapes AS shape
  ON shape.feed_id = trip.feed_id
 AND shape.shape_id = trip.shape_id
JOIN core.gtfs_stops AS stop
  ON stop.feed_id = trip.feed_id
WHERE stop_time.feed_id = trip.feed_id
  AND stop_time.trip_id = trip.trip_id
  AND stop.stop_id = stop_time.stop_id
  AND stop.location IS NOT NULL
"""


def upgrade() -> None:
    op.add_column(
        "gtfs_stop_times",
        sa.Column("shape_position", sa.Float()),
        schema="core",
    )
    op.add_column(
        "gtfs_stop_times",
        sa.Column("distance_to_shape_m", sa.Float()),
        schema="core",
    )
    op.execute(PROJECT_STOP_TIMES_SQL)
    op.create_index(
        "ix_gtfs_stop_times_trip_shape_position",
        "gtfs_stop_times",
        ["feed_id", "trip_id", "shape_position"],
        schema="core",
    )

    for column in (
        sa.Column("projection_quality", sa.String(length=30)),
        sa.Column("current_origin_stop_id", sa.String(length=100)),
        sa.Column("current_destination_stop_id", sa.String(length=100)),
        sa.Column("current_origin_stop_sequence", sa.Integer()),
        sa.Column("current_destination_stop_sequence", sa.Integer()),
    ):
        op.add_column("vehicle_current_states", column, schema="realtime")
    op.create_check_constraint(
        "ck_vehicle_current_states_shape_position",
        "vehicle_current_states",
        "shape_position IS NULL OR shape_position BETWEEN 0 AND 1",
        schema="realtime",
    )
    op.create_check_constraint(
        "ck_vehicle_current_states_shape_distance",
        "vehicle_current_states",
        "distance_to_shape_m IS NULL OR distance_to_shape_m >= 0",
        schema="realtime",
    )
    op.create_check_constraint(
        "ck_vehicle_current_states_projection_quality",
        "vehicle_current_states",
        "projection_quality IS NULL OR projection_quality IN "
        "('valid', 'reduced', 'fallback_required')",
        schema="realtime",
    )


def downgrade() -> None:
    for constraint_name in (
        "ck_vehicle_current_states_projection_quality",
        "ck_vehicle_current_states_shape_distance",
        "ck_vehicle_current_states_shape_position",
    ):
        op.drop_constraint(
            constraint_name,
            "vehicle_current_states",
            schema="realtime",
            type_="check",
        )
    for column_name in (
        "current_destination_stop_sequence",
        "current_origin_stop_sequence",
        "current_destination_stop_id",
        "current_origin_stop_id",
        "projection_quality",
    ):
        op.drop_column("vehicle_current_states", column_name, schema="realtime")

    op.drop_index(
        "ix_gtfs_stop_times_trip_shape_position",
        table_name="gtfs_stop_times",
        schema="core",
    )
    op.drop_column("gtfs_stop_times", "distance_to_shape_m", schema="core")
    op.drop_column("gtfs_stop_times", "shape_position", schema="core")
