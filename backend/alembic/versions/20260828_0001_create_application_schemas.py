from collections.abc import Sequence

from alembic import op
from sqlalchemy.schema import CreateSchema, DropSchema

revision: str = "20260828_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPLICATION_SCHEMAS = (
    "raw",
    "core",
    "realtime",
    "analytics",
    "audit",
)


def upgrade() -> None:
    for schema_name in APPLICATION_SCHEMAS:
        op.execute(
            CreateSchema(
                schema_name,
                if_not_exists=True,
            )
        )


def downgrade() -> None:
    for schema_name in reversed(APPLICATION_SCHEMAS):
        op.execute(
            DropSchema(
                schema_name,
                cascade=True,
                if_exists=True,
            )
        )
