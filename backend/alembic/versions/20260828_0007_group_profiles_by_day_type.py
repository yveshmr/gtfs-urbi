from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0007"
down_revision: str | None = "20260828_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "segment_profiles_5m_pkey",
        "segment_profiles_5m",
        schema="analytics",
        type_="primary",
    )
    op.drop_constraint(
        "ck_segment_profiles_5m_weekday",
        "segment_profiles_5m",
        schema="analytics",
        type_="check",
    )
    op.alter_column(
        "segment_profiles_5m",
        "service_weekday",
        new_column_name="day_type",
        existing_type=sa.SmallInteger(),
        type_=sa.String(length=10),
        postgresql_using=(
            "CASE WHEN service_weekday BETWEEN 1 AND 5 THEN 'weekday' "
            "WHEN service_weekday = 6 THEN 'saturday' ELSE 'sunday' END"
        ),
        existing_nullable=False,
        schema="analytics",
    )
    op.create_check_constraint(
        "ck_segment_profiles_5m_day_type",
        "segment_profiles_5m",
        "day_type IN ('weekday', 'saturday', 'sunday')",
        schema="analytics",
    )
    op.create_primary_key(
        "segment_profiles_5m_pkey",
        "segment_profiles_5m",
        ["metric_key", "day_type", "slot_index"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_constraint(
        "segment_profiles_5m_pkey",
        "segment_profiles_5m",
        schema="analytics",
        type_="primary",
    )
    op.drop_constraint(
        "ck_segment_profiles_5m_day_type",
        "segment_profiles_5m",
        schema="analytics",
        type_="check",
    )
    op.alter_column(
        "segment_profiles_5m",
        "day_type",
        new_column_name="service_weekday",
        existing_type=sa.String(length=10),
        type_=sa.SmallInteger(),
        postgresql_using=("CASE day_type WHEN 'weekday' THEN 1 WHEN 'saturday' THEN 6 ELSE 7 END"),
        existing_nullable=False,
        schema="analytics",
    )
    op.create_check_constraint(
        "ck_segment_profiles_5m_weekday",
        "segment_profiles_5m",
        "service_weekday BETWEEN 1 AND 7",
        schema="analytics",
    )
    op.create_primary_key(
        "segment_profiles_5m_pkey",
        "segment_profiles_5m",
        ["metric_key", "service_weekday", "slot_index"],
        schema="analytics",
    )
