from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0012"
down_revision: str | None = "20260828_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BACKFILL_BOUNDARY_QUALITY_SQL = """
WITH shape_totals AS (
    SELECT feed_id, shape_id, max(end_distance_m) AS total_distance_m
    FROM core.gtfs_shape_segments
    GROUP BY feed_id, shape_id
)
UPDATE core.gtfs_stop_times AS stop_time
SET
    shape_progress_m = stop_time.shape_position * shape_total.total_distance_m,
    shape_projection_quality = CASE
        WHEN stop_time.distance_to_shape_m <= 30 THEN 'valid'
        WHEN stop_time.distance_to_shape_m <= 50 THEN 'reduced'
        ELSE 'fallback_required'
    END
FROM core.gtfs_trips AS trip
JOIN shape_totals AS shape_total
  ON shape_total.feed_id = trip.feed_id
 AND shape_total.shape_id = trip.shape_id
WHERE stop_time.feed_id = trip.feed_id
  AND stop_time.trip_id = trip.trip_id
  AND stop_time.shape_position IS NOT NULL
  AND stop_time.distance_to_shape_m IS NOT NULL
"""


def upgrade() -> None:
    op.add_column(
        "gtfs_stop_times",
        sa.Column("shape_progress_m", sa.Float()),
        schema="core",
    )
    op.add_column(
        "gtfs_stop_times",
        sa.Column("shape_projection_quality", sa.String(length=30)),
        schema="core",
    )
    op.create_check_constraint(
        "ck_gtfs_stop_times_shape_progress",
        "gtfs_stop_times",
        "shape_progress_m IS NULL OR shape_progress_m >= 0",
        schema="core",
    )
    op.create_check_constraint(
        "ck_gtfs_stop_times_projection_quality",
        "gtfs_stop_times",
        "shape_projection_quality IS NULL OR shape_projection_quality IN "
        "('valid', 'reduced', 'fallback_required')",
        schema="core",
    )
    op.execute(BACKFILL_BOUNDARY_QUALITY_SQL)
    op.create_index(
        "ix_gtfs_stop_times_trip_shape_progress",
        "gtfs_stop_times",
        ["feed_id", "trip_id", "shape_progress_m"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gtfs_stop_times_trip_shape_progress",
        table_name="gtfs_stop_times",
        schema="core",
    )
    op.drop_constraint(
        "ck_gtfs_stop_times_projection_quality",
        "gtfs_stop_times",
        schema="core",
        type_="check",
    )
    op.drop_constraint(
        "ck_gtfs_stop_times_shape_progress",
        "gtfs_stop_times",
        schema="core",
        type_="check",
    )
    op.drop_column("gtfs_stop_times", "shape_projection_quality", schema="core")
    op.drop_column("gtfs_stop_times", "shape_progress_m", schema="core")
