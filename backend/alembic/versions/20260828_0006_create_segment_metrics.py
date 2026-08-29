from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0006"
down_revision: str | None = "20260828_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns(*, profile: bool) -> list[sa.Column]:
    columns: list[sa.Column] = [
        sa.Column("metric_key", sa.String(length=64), nullable=False),
    ]
    if profile:
        columns.extend(
            [
                sa.Column("service_weekday", sa.SmallInteger(), nullable=False),
                sa.Column("slot_index", sa.SmallInteger(), nullable=False),
            ]
        )
    columns.extend(
        [
            sa.Column("scope", sa.String(length=10), nullable=False),
            sa.Column("origin_stop_id", sa.String(length=100), nullable=False),
            sa.Column("destination_stop_id", sa.String(length=100), nullable=False),
            sa.Column("route_id", sa.String(length=100)),
            sa.Column("direction_id", sa.SmallInteger()),
        ]
    )
    return columns


def _sample_columns() -> list[sa.Column]:
    return [
        sa.Column("sample_count_total", sa.Integer(), nullable=False),
        sa.Column("sample_count_accepted", sa.Integer(), nullable=False),
        sa.Column("sample_count_rejected", sa.Integer(), nullable=False),
        sa.Column("mean_seconds", sa.Float()),
        sa.Column("median_seconds", sa.Float()),
        sa.Column("standard_deviation_seconds", sa.Float()),
        sa.Column("minimum_seconds", sa.Float()),
        sa.Column("maximum_seconds", sa.Float()),
        sa.Column("reliability", sa.Float(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "segment_live_metrics_5m",
        *_identity_columns(profile=False),
        sa.Column("source_feed_id", sa.Uuid(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        *_sample_columns(),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_live_metrics_5m_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_live_metrics_5m_dimensions",
        ),
        sa.CheckConstraint(
            "window_end = window_start + INTERVAL '5 minutes'",
            name="ck_segment_live_metrics_5m_window",
        ),
        sa.CheckConstraint(
            "sample_count_total = sample_count_accepted + sample_count_rejected",
            name="ck_segment_live_metrics_5m_sample_counts",
        ),
        sa.CheckConstraint(
            "sample_count_total > 0",
            name="ck_segment_live_metrics_5m_has_samples",
        ),
        sa.CheckConstraint(
            "reliability BETWEEN 0 AND 1",
            name="ck_segment_live_metrics_5m_reliability",
        ),
        sa.CheckConstraint(
            "status IN ('insufficient', 'low', 'medium', 'high', 'anomalous')",
            name="ck_segment_live_metrics_5m_status",
        ),
        sa.ForeignKeyConstraint(
            ["source_feed_id"],
            ["core.gtfs_feeds.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("metric_key"),
        schema="analytics",
    )
    op.create_index(
        "ix_segment_live_metrics_5m_stops",
        "segment_live_metrics_5m",
        ["origin_stop_id", "destination_stop_id"],
        schema="analytics",
    )
    op.create_index(
        "ix_segment_live_metrics_5m_service",
        "segment_live_metrics_5m",
        ["route_id", "direction_id"],
        schema="analytics",
    )
    op.create_index(
        "ix_segment_live_metrics_5m_window_start",
        "segment_live_metrics_5m",
        ["window_start"],
        schema="analytics",
    )

    op.create_table(
        "segment_profiles_5m",
        *_identity_columns(profile=True),
        sa.Column("last_source_feed_id", sa.Uuid(), nullable=False),
        *_sample_columns(),
        sa.Column("m2_seconds", sa.Float(), nullable=False),
        sa.Column("mad_seconds", sa.Float()),
        sa.Column("ewma_seconds", sa.Float()),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('physical', 'service')",
            name="ck_segment_profiles_5m_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'physical' AND route_id IS NULL AND direction_id IS NULL) OR "
            "(scope = 'service' AND route_id IS NOT NULL AND direction_id IS NOT NULL)",
            name="ck_segment_profiles_5m_dimensions",
        ),
        sa.CheckConstraint(
            "service_weekday BETWEEN 1 AND 7",
            name="ck_segment_profiles_5m_weekday",
        ),
        sa.CheckConstraint(
            "slot_index BETWEEN 0 AND 287",
            name="ck_segment_profiles_5m_slot",
        ),
        sa.CheckConstraint(
            "sample_count_total = sample_count_accepted + sample_count_rejected",
            name="ck_segment_profiles_5m_sample_counts",
        ),
        sa.CheckConstraint(
            "sample_count_total >= 0",
            name="ck_segment_profiles_5m_nonnegative_samples",
        ),
        sa.CheckConstraint(
            "reliability BETWEEN 0 AND 1",
            name="ck_segment_profiles_5m_reliability",
        ),
        sa.ForeignKeyConstraint(
            ["last_source_feed_id"],
            ["core.gtfs_feeds.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("metric_key", "service_weekday", "slot_index"),
        schema="analytics",
    )
    op.create_index(
        "ix_segment_profiles_5m_stops",
        "segment_profiles_5m",
        ["origin_stop_id", "destination_stop_id"],
        schema="analytics",
    )
    op.create_index(
        "ix_segment_profiles_5m_service",
        "segment_profiles_5m",
        ["route_id", "direction_id"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_segment_profiles_5m_service",
        table_name="segment_profiles_5m",
        schema="analytics",
    )
    op.drop_index(
        "ix_segment_profiles_5m_stops",
        table_name="segment_profiles_5m",
        schema="analytics",
    )
    op.drop_table("segment_profiles_5m", schema="analytics")

    op.drop_index(
        "ix_segment_live_metrics_5m_window_start",
        table_name="segment_live_metrics_5m",
        schema="analytics",
    )
    op.drop_index(
        "ix_segment_live_metrics_5m_service",
        table_name="segment_live_metrics_5m",
        schema="analytics",
    )
    op.drop_index(
        "ix_segment_live_metrics_5m_stops",
        table_name="segment_live_metrics_5m",
        schema="analytics",
    )
    op.drop_table("segment_live_metrics_5m", schema="analytics")
