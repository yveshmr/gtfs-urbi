from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_0019"
down_revision: str | None = "20260829_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_eta_snapshots",
        sa.Column("vehicle_prefix", sa.String(length=50), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trip_id", sa.String(length=150), nullable=False),
        sa.Column("route_id", sa.String(length=100), nullable=False),
        sa.Column("direction_id", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_prefix"],
            ["realtime.vehicle_current_states.vehicle_prefix"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vehicle_prefix"),
        schema="realtime",
    )
    op.create_index(
        "ix_vehicle_eta_snapshots_generated_at",
        "vehicle_eta_snapshots",
        ["generated_at"],
        schema="realtime",
    )
    op.create_index(
        "ix_vehicle_eta_snapshots_route",
        "vehicle_eta_snapshots",
        ["route_id", "direction_id"],
        schema="realtime",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_eta_snapshots_route",
        table_name="vehicle_eta_snapshots",
        schema="realtime",
    )
    op.drop_index(
        "ix_vehicle_eta_snapshots_generated_at",
        table_name="vehicle_eta_snapshots",
        schema="realtime",
    )
    op.drop_table("vehicle_eta_snapshots", schema="realtime")
