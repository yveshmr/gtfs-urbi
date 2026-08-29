from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0005"
down_revision: str | None = "20260828_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_current_states",
        sa.Column("vehicle_prefix", sa.String(length=50), nullable=False),
        sa.Column("imei", sa.String(length=50)),
        sa.Column("source_timestamp", sa.DateTime(timezone=True)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
            ),
        ),
        sa.Column("gps_direction", sa.Float()),
        sa.Column("speed_kmh", sa.Float()),
        sa.Column("current_line", sa.String(length=100)),
        sa.Column("normalized_current_line", sa.String(length=100)),
        sa.Column("current_planned_time", sa.String(length=100)),
        sa.Column("current_direction", sa.String(length=20)),
        sa.Column("current_schedule_position", sa.Text()),
        sa.Column("current_actual_time", sa.String(length=100)),
        sa.Column("next_planned_time", sa.String(length=100)),
        sa.Column("next_trip_point", sa.Text()),
        sa.Column("next_schedule_position", sa.Text()),
        sa.Column("next_line", sa.String(length=100)),
        sa.Column("next_direction", sa.String(length=20)),
        sa.Column("next_trip_destination", sa.Text()),
        sa.Column("source_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_vehicle_current_states_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_vehicle_current_states_longitude",
        ),
        sa.CheckConstraint(
            "speed_kmh IS NULL OR speed_kmh >= 0",
            name="ck_vehicle_current_states_speed",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["audit.ingestion_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("vehicle_prefix"),
        schema="realtime",
    )
    op.create_index(
        "ix_vehicle_current_states_source_timestamp",
        "vehicle_current_states",
        ["source_timestamp"],
        schema="realtime",
    )
    op.create_index(
        "ix_vehicle_current_states_current_line",
        "vehicle_current_states",
        ["normalized_current_line"],
        schema="realtime",
    )
    op.create_index(
        "ix_vehicle_current_states_location",
        "vehicle_current_states",
        ["location"],
        schema="realtime",
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_current_states_location",
        table_name="vehicle_current_states",
        schema="realtime",
        postgresql_using="gist",
    )
    op.drop_index(
        "ix_vehicle_current_states_current_line",
        table_name="vehicle_current_states",
        schema="realtime",
    )
    op.drop_index(
        "ix_vehicle_current_states_source_timestamp",
        table_name="vehicle_current_states",
        schema="realtime",
    )
    op.drop_table("vehicle_current_states", schema="realtime")
