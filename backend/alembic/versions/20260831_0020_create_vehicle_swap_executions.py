from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0020"
down_revision: str | None = "20260829_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_swap_executions",
        sa.Column("execution_key", sa.String(length=64), nullable=False),
        sa.Column("group_id", sa.String(length=150), nullable=False),
        sa.Column("terminal_id", sa.Text(), nullable=False),
        sa.Column("snapshot_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("executed_by", sa.String(length=100), nullable=False),
        sa.Column(
            "group_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("execution_key"),
        schema="audit",
    )
    op.create_index(
        "ix_vehicle_swap_executions_executed_at",
        "vehicle_swap_executions",
        ["executed_at"],
        schema="audit",
    )
    op.create_index(
        "ix_vehicle_swap_executions_terminal",
        "vehicle_swap_executions",
        ["terminal_id", "executed_at"],
        schema="audit",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_swap_executions_terminal",
        table_name="vehicle_swap_executions",
        schema="audit",
    )
    op.drop_index(
        "ix_vehicle_swap_executions_executed_at",
        table_name="vehicle_swap_executions",
        schema="audit",
    )
    op.drop_table("vehicle_swap_executions", schema="audit")
