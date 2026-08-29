from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0013"
down_revision: str | None = "20260828_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("shape_progress_m", sa.Float()),
        sa.Column("last_boundary_stop_id", sa.String(length=100)),
        sa.Column("last_boundary_stop_sequence", sa.Integer()),
        sa.Column("last_boundary_progress_m", sa.Float()),
        sa.Column("last_boundary_crossed_at", sa.DateTime(timezone=True)),
        sa.Column("last_boundary_observation_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("vehicle_current_states", column, schema="realtime")
    op.create_check_constraint(
        "ck_vehicle_current_states_shape_progress",
        "vehicle_current_states",
        "shape_progress_m IS NULL OR shape_progress_m >= 0",
        schema="realtime",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_vehicle_current_states_shape_progress",
        "vehicle_current_states",
        schema="realtime",
        type_="check",
    )
    for column_name in (
        "last_boundary_observation_at",
        "last_boundary_crossed_at",
        "last_boundary_progress_m",
        "last_boundary_stop_sequence",
        "last_boundary_stop_id",
        "shape_progress_m",
    ):
        op.drop_column("vehicle_current_states", column_name, schema="realtime")
