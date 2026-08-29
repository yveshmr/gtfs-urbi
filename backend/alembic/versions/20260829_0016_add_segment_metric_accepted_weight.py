from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0016"
down_revision: str | None = "20260829_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("segment_live_metrics_5m", "segment_profiles_5m"):
        op.add_column(
            table_name,
            sa.Column(
                "accepted_weight",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
            schema="analytics",
        )
        op.create_check_constraint(
            f"ck_{table_name}_accepted_weight",
            table_name,
            "accepted_weight >= 0",
            schema="analytics",
        )


def downgrade() -> None:
    for table_name in ("segment_profiles_5m", "segment_live_metrics_5m"):
        op.drop_constraint(
            f"ck_{table_name}_accepted_weight",
            table_name,
            schema="analytics",
            type_="check",
        )
        op.drop_column(table_name, "accepted_weight", schema="analytics")
