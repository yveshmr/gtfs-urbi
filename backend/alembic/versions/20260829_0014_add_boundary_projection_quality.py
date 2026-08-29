from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0014"
down_revision: str | None = "20260828_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vehicle_current_states",
        sa.Column("last_boundary_projection_quality", sa.String(length=30)),
        schema="realtime",
    )
    op.create_check_constraint(
        "ck_vehicle_current_states_boundary_projection_quality",
        "vehicle_current_states",
        "last_boundary_projection_quality IS NULL OR "
        "last_boundary_projection_quality IN ('valid', 'reduced', 'fallback_required')",
        schema="realtime",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_vehicle_current_states_boundary_projection_quality",
        "vehicle_current_states",
        schema="realtime",
        type_="check",
    )
    op.drop_column(
        "vehicle_current_states",
        "last_boundary_projection_quality",
        schema="realtime",
    )
