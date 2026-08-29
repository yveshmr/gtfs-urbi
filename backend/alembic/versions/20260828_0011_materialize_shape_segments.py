from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "20260828_0011"
down_revision: str | None = "20260828_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MATERIALIZE_SHAPE_SEGMENTS_SQL = """
WITH point_pairs AS (
    SELECT
        point.feed_id,
        point.shape_id,
        point.sequence AS segment_sequence,
        point.location AS start_location,
        lead(point.location) OVER (
            PARTITION BY point.feed_id, point.shape_id
            ORDER BY point.sequence
        ) AS end_location
    FROM core.gtfs_shape_points AS point
), measured AS (
    SELECT
        feed_id,
        shape_id,
        segment_sequence,
        ST_MakeLine(start_location, end_location) AS geometry,
        ST_Distance(start_location::geography, end_location::geography) AS segment_length_m,
        degrees(ST_Azimuth(start_location, end_location)) AS bearing_degrees
    FROM point_pairs
    WHERE end_location IS NOT NULL
      AND NOT ST_Equals(start_location, end_location)
), positioned AS (
    SELECT
        measured.*,
        coalesce(
            sum(segment_length_m) OVER (
                PARTITION BY feed_id, shape_id
                ORDER BY segment_sequence
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ),
            0
        ) AS start_distance_m,
        sum(segment_length_m) OVER (
            PARTITION BY feed_id, shape_id
        ) AS total_distance_m
    FROM measured
)
INSERT INTO core.gtfs_shape_segments (
    feed_id,
    shape_id,
    segment_sequence,
    geometry,
    segment_length_m,
    start_distance_m,
    end_distance_m,
    start_fraction,
    end_fraction,
    bearing_degrees
)
SELECT
    feed_id,
    shape_id,
    segment_sequence,
    geometry,
    segment_length_m,
    start_distance_m,
    start_distance_m + segment_length_m,
    start_distance_m / total_distance_m,
    (start_distance_m + segment_length_m) / total_distance_m,
    bearing_degrees
FROM positioned
WHERE total_distance_m > 0
"""


def upgrade() -> None:
    op.create_table(
        "gtfs_shape_segments",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("shape_id", sa.String(length=100), nullable=False),
        sa.Column("segment_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "geometry",
            Geometry("LINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("segment_length_m", sa.Float(), nullable=False),
        sa.Column("start_distance_m", sa.Float(), nullable=False),
        sa.Column("end_distance_m", sa.Float(), nullable=False),
        sa.Column("start_fraction", sa.Float(), nullable=False),
        sa.Column("end_fraction", sa.Float(), nullable=False),
        sa.Column("bearing_degrees", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "segment_sequence >= 0",
            name="ck_gtfs_shape_segments_sequence",
        ),
        sa.CheckConstraint(
            "segment_length_m > 0",
            name="ck_gtfs_shape_segments_length",
        ),
        sa.CheckConstraint(
            "start_distance_m >= 0 AND end_distance_m > start_distance_m",
            name="ck_gtfs_shape_segments_distances",
        ),
        sa.CheckConstraint(
            "start_fraction BETWEEN 0 AND 1 "
            "AND end_fraction BETWEEN 0 AND 1 "
            "AND end_fraction > start_fraction",
            name="ck_gtfs_shape_segments_fractions",
        ),
        sa.ForeignKeyConstraint(
            ["feed_id", "shape_id"],
            ["core.gtfs_shapes.feed_id", "core.gtfs_shapes.shape_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feed_id", "shape_id", "segment_sequence"),
        schema="core",
    )
    op.create_index(
        "ix_gtfs_shape_segments_geometry",
        "gtfs_shape_segments",
        ["geometry"],
        schema="core",
        postgresql_using="gist",
    )
    op.execute(MATERIALIZE_SHAPE_SEGMENTS_SQL)


def downgrade() -> None:
    op.drop_index(
        "ix_gtfs_shape_segments_geometry",
        table_name="gtfs_shape_segments",
        schema="core",
    )
    op.drop_table("gtfs_shape_segments", schema="core")
