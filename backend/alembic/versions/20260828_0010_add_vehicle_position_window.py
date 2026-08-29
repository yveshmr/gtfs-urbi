from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0010"
down_revision: str | None = "20260828_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vehicle_current_states",
        sa.Column("previous_state_1", postgresql.JSONB(astext_type=sa.Text())),
        schema="realtime",
    )
    op.add_column(
        "vehicle_current_states",
        sa.Column("previous_state_2", postgresql.JSONB(astext_type=sa.Text())),
        schema="realtime",
    )
    op.add_column(
        "vehicle_current_states",
        sa.Column(
            "position_sample_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        schema="realtime",
    )
    op.add_column(
        "vehicle_current_states",
        sa.Column(
            "map_match_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'collecting'"),
        ),
        schema="realtime",
    )
    op.create_check_constraint(
        "ck_vehicle_current_states_sample_count",
        "vehicle_current_states",
        "position_sample_count BETWEEN 1 AND 3",
        schema="realtime",
    )
    op.create_check_constraint(
        "ck_vehicle_current_states_map_match_status",
        "vehicle_current_states",
        "map_match_status IN ('collecting', 'resolved', 'ambiguous', 'fallback_required')",
        schema="realtime",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_vehicle_current_states_map_match_status",
        "vehicle_current_states",
        schema="realtime",
        type_="check",
    )
    op.drop_constraint(
        "ck_vehicle_current_states_sample_count",
        "vehicle_current_states",
        schema="realtime",
        type_="check",
    )
    op.drop_column("vehicle_current_states", "map_match_status", schema="realtime")
    op.drop_column("vehicle_current_states", "position_sample_count", schema="realtime")
    op.drop_column("vehicle_current_states", "previous_state_2", schema="realtime")
    op.drop_column("vehicle_current_states", "previous_state_1", schema="realtime")
