from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0021"
down_revision: str | None = "20260831_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vehicle_current_states",
        sa.Column("low_speed_since", sa.DateTime(timezone=True), nullable=True),
        schema="realtime",
    )

    op.rename_table(
        "vehicle_swap_executions",
        "vehicle_swap_decisions",
        schema="audit",
    )
    op.execute(
        "ALTER INDEX audit.ix_vehicle_swap_executions_executed_at "
        "RENAME TO ix_vehicle_swap_decisions_updated_at"
    )
    op.execute(
        "ALTER INDEX audit.ix_vehicle_swap_executions_terminal "
        "RENAME TO ix_vehicle_swap_decisions_terminal"
    )
    op.alter_column(
        "vehicle_swap_decisions",
        "executed_at",
        new_column_name="updated_at",
        schema="audit",
    )
    op.alter_column(
        "vehicle_swap_decisions",
        "executed_by",
        new_column_name="updated_by",
        schema="audit",
    )
    op.add_column(
        "vehicle_swap_decisions",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="executed",
            nullable=False,
        ),
        schema="audit",
    )
    op.add_column(
        "vehicle_swap_decisions",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        schema="audit",
    )
    op.create_check_constraint(
        "ck_vehicle_swap_decisions_status",
        "vehicle_swap_decisions",
        "status IN ('in_analysis', 'claimed', 'executed', 'rejected')",
        schema="audit",
    )
    op.alter_column(
        "vehicle_swap_decisions",
        "status",
        server_default=None,
        schema="audit",
    )
    op.create_table(
        "vehicle_swap_decision_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["execution_key"],
            ["audit.vehicle_swap_decisions.execution_key"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="audit",
    )
    op.create_index(
        "ix_vehicle_swap_decision_events_key",
        "vehicle_swap_decision_events",
        ["execution_key", "occurred_at"],
        schema="audit",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_swap_decision_events_key",
        table_name="vehicle_swap_decision_events",
        schema="audit",
    )
    op.drop_table("vehicle_swap_decision_events", schema="audit")
    op.drop_constraint(
        "ck_vehicle_swap_decisions_status",
        "vehicle_swap_decisions",
        schema="audit",
        type_="check",
    )
    op.drop_column("vehicle_swap_decisions", "rejection_reason", schema="audit")
    op.drop_column("vehicle_swap_decisions", "status", schema="audit")
    op.alter_column(
        "vehicle_swap_decisions",
        "updated_by",
        new_column_name="executed_by",
        schema="audit",
    )
    op.alter_column(
        "vehicle_swap_decisions",
        "updated_at",
        new_column_name="executed_at",
        schema="audit",
    )
    op.execute(
        "ALTER INDEX audit.ix_vehicle_swap_decisions_terminal "
        "RENAME TO ix_vehicle_swap_executions_terminal"
    )
    op.execute(
        "ALTER INDEX audit.ix_vehicle_swap_decisions_updated_at "
        "RENAME TO ix_vehicle_swap_executions_executed_at"
    )
    op.rename_table(
        "vehicle_swap_decisions",
        "vehicle_swap_executions",
        schema="audit",
    )
    op.drop_column("vehicle_current_states", "low_speed_since", schema="realtime")
