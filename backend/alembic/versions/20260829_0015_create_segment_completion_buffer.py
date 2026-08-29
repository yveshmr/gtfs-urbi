from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0015"
down_revision: str | None = "20260829_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "segment_completion_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("origin_stop_id", sa.String(length=100), nullable=False),
        sa.Column("destination_stop_id", sa.String(length=100), nullable=False),
        sa.Column("route_id", sa.String(length=100)),
        sa.Column("direction_id", sa.SmallInteger()),
        sa.Column("source_feed_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("average_speed_kmh", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_completion_observations_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_completion_observations_dimensions",
        ),
        sa.CheckConstraint(
            "duration_seconds > 0 AND distance_m > 0 AND average_speed_kmh > 0",
            name="ck_segment_completion_observations_measurements",
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'reduced')",
            name="ck_segment_completion_observations_confidence",
        ),
        sa.CheckConstraint(
            "(accepted AND weight > 0 AND weight <= 1 AND rejection_reason IS NULL) "
            "OR (NOT accepted AND weight = 0 AND rejection_reason IS NOT NULL)",
            name="ck_segment_completion_observations_assessment",
        ),
        sa.CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('speed_over_80', 'mad_outlier', 'invalid_measurement')",
            name="ck_segment_completion_observations_rejection_reason",
        ),
        sa.CheckConstraint(
            "expires_at = completed_at + INTERVAL '1 hour'",
            name="ck_segment_completion_observations_retention",
        ),
        sa.ForeignKeyConstraint(
            ["source_feed_id"],
            ["core.gtfs_feeds.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="analytics",
    )
    op.create_index(
        "ix_segment_completion_observations_metric_completed",
        "segment_completion_observations",
        ["metric_key", "completed_at"],
        schema="analytics",
    )
    op.create_index(
        "ix_segment_completion_observations_expires_at",
        "segment_completion_observations",
        ["expires_at"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_segment_completion_observations_expires_at",
        table_name="segment_completion_observations",
        schema="analytics",
    )
    op.drop_index(
        "ix_segment_completion_observations_metric_completed",
        table_name="segment_completion_observations",
        schema="analytics",
    )
    op.drop_table("segment_completion_observations", schema="analytics")
