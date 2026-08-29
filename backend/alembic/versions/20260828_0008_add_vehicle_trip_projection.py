from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0008"
down_revision: str | None = "20260828_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("feed_id", sa.Uuid()),
        sa.Column("trip_id", sa.String(length=150)),
        sa.Column("route_id", sa.String(length=100)),
        sa.Column("shape_id", sa.String(length=100)),
        sa.Column("correlation_status", sa.String(length=30)),
        sa.Column("correlation_reason", sa.String(length=50)),
        sa.Column("correlation_level", sa.Integer()),
        sa.Column(
            "correlation_candidate_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("shape_position", sa.Float()),
        sa.Column("distance_to_shape_m", sa.Float()),
        sa.Column(
            "projected_location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
            ),
        ),
        sa.Column("projected_at", sa.DateTime(timezone=True)),
    )
    for column in columns:
        op.add_column("vehicle_current_states", column, schema="realtime")

    op.create_foreign_key(
        "fk_vehicle_current_states_trip",
        "vehicle_current_states",
        "gtfs_trips",
        ["feed_id", "trip_id"],
        ["feed_id", "trip_id"],
        source_schema="realtime",
        referent_schema="core",
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_vehicle_current_states_trip",
        "vehicle_current_states",
        ["feed_id", "trip_id"],
        schema="realtime",
    )
    op.create_index(
        "ix_vehicle_current_states_correlation_status",
        "vehicle_current_states",
        ["correlation_status"],
        schema="realtime",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_current_states_correlation_status",
        table_name="vehicle_current_states",
        schema="realtime",
    )
    op.drop_index(
        "ix_vehicle_current_states_trip",
        table_name="vehicle_current_states",
        schema="realtime",
    )
    op.drop_constraint(
        "fk_vehicle_current_states_trip",
        "vehicle_current_states",
        schema="realtime",
        type_="foreignkey",
    )
    for column_name in (
        "projected_at",
        "projected_location",
        "distance_to_shape_m",
        "shape_position",
        "correlation_candidate_count",
        "correlation_level",
        "correlation_reason",
        "correlation_status",
        "shape_id",
        "route_id",
        "trip_id",
        "feed_id",
    ):
        op.drop_column("vehicle_current_states", column_name, schema="realtime")
