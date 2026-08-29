from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0017"
down_revision: str | None = "20260829_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "segment_daily_metrics_5m",
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("slot_index", sa.SmallInteger(), nullable=False),
        sa.Column("day_type", sa.String(length=10), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("origin_stop_id", sa.String(length=100), nullable=False),
        sa.Column("destination_stop_id", sa.String(length=100), nullable=False),
        sa.Column("route_id", sa.String(length=100)),
        sa.Column("direction_id", sa.SmallInteger()),
        sa.Column("source_feed_id", sa.Uuid(), nullable=False),
        sa.Column("sample_count_total", sa.Integer(), nullable=False),
        sa.Column("sample_count_accepted", sa.Integer(), nullable=False),
        sa.Column("sample_count_rejected", sa.Integer(), nullable=False),
        sa.Column("accepted_weight", sa.Float(), nullable=False),
        sa.Column("mean_seconds", sa.Float()),
        sa.Column("median_seconds", sa.Float()),
        sa.Column("standard_deviation_seconds", sa.Float()),
        sa.Column("minimum_seconds", sa.Float()),
        sa.Column("maximum_seconds", sa.Float()),
        sa.Column("m2_seconds", sa.Float(), nullable=False),
        sa.Column("reliability", sa.Float(), nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_daily_metrics_5m_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_daily_metrics_5m_dimensions",
        ),
        sa.CheckConstraint(
            "day_type IN ('weekday', 'saturday', 'sunday')",
            name="ck_segment_daily_metrics_5m_day_type",
        ),
        sa.CheckConstraint(
            "slot_index BETWEEN 0 AND 287",
            name="ck_segment_daily_metrics_5m_slot",
        ),
        sa.CheckConstraint(
            "sample_count_total = sample_count_accepted + sample_count_rejected",
            name="ck_segment_daily_metrics_5m_sample_counts",
        ),
        sa.CheckConstraint(
            "sample_count_total > 0 AND accepted_weight >= 0",
            name="ck_segment_daily_metrics_5m_samples",
        ),
        sa.CheckConstraint(
            "reliability BETWEEN 0 AND 1",
            name="ck_segment_daily_metrics_5m_reliability",
        ),
        sa.ForeignKeyConstraint(
            ["source_feed_id"],
            ["core.gtfs_feeds.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("metric_key", "service_date", "slot_index"),
        schema="analytics",
    )
    op.create_index(
        "ix_segment_daily_metrics_5m_lookup",
        "segment_daily_metrics_5m",
        ["day_type", "slot_index", "service_date"],
        schema="analytics",
    )
    op.create_index(
        "ix_segment_daily_metrics_5m_service_date",
        "segment_daily_metrics_5m",
        ["service_date"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_segment_daily_metrics_5m_service_date",
        table_name="segment_daily_metrics_5m",
        schema="analytics",
    )
    op.drop_index(
        "ix_segment_daily_metrics_5m_lookup",
        table_name="segment_daily_metrics_5m",
        schema="analytics",
    )
    op.drop_table("segment_daily_metrics_5m", schema="analytics")
