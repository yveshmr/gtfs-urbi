from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0018"
down_revision: str | None = "20260829_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "segment_profiles_5m",
        sa.Column("reference_start_date", sa.Date()),
        schema="analytics",
    )
    op.add_column(
        "segment_profiles_5m",
        sa.Column("reference_end_date", sa.Date()),
        schema="analytics",
    )
    op.execute(
        "UPDATE analytics.segment_profiles_5m "
        "SET reference_start_date = CURRENT_DATE - 7, "
        "reference_end_date = CURRENT_DATE - 1"
    )
    op.alter_column(
        "segment_profiles_5m",
        "reference_start_date",
        nullable=False,
        schema="analytics",
    )
    op.alter_column(
        "segment_profiles_5m",
        "reference_end_date",
        nullable=False,
        schema="analytics",
    )
    op.create_check_constraint(
        "ck_segment_profiles_5m_reference_period",
        "segment_profiles_5m",
        "reference_end_date = reference_start_date + 6",
        schema="analytics",
    )

    op.create_table(
        "segment_profile_refresh_state",
        sa.Column("profile_name", sa.String(length=50), nullable=False),
        sa.Column("reference_start_date", sa.Date(), nullable=False),
        sa.Column("reference_end_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reference_end_date = reference_start_date + 6",
            name="ck_segment_profile_refresh_state_period",
        ),
        sa.PrimaryKeyConstraint("profile_name"),
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_table("segment_profile_refresh_state", schema="analytics")
    op.drop_constraint(
        "ck_segment_profiles_5m_reference_period",
        "segment_profiles_5m",
        schema="analytics",
        type_="check",
    )
    op.drop_column("segment_profiles_5m", "reference_end_date", schema="analytics")
    op.drop_column("segment_profiles_5m", "reference_start_date", schema="analytics")
