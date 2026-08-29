from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0002"
down_revision: str | None = "20260828_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "source_system",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "resource_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "records_received",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "records_written",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "http_status",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name="ck_ingestion_runs_status",
        ),
        sa.CheckConstraint(
            "records_received >= 0",
            name="ck_ingestion_runs_records_received",
        ),
        sa.CheckConstraint(
            "records_written >= 0",
            name="ck_ingestion_runs_records_written",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_ingestion_runs_valid_period",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="audit",
    )

    op.create_index(
        "ix_ingestion_runs_source_started_at",
        "ingestion_runs",
        ["source_system", "started_at"],
        schema="audit",
    )
    op.create_index(
        "ix_ingestion_runs_status",
        "ingestion_runs",
        ["status"],
        schema="audit",
    )

    op.create_table(
        "api_responses",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "endpoint_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "source_model",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "source_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "http_status",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "payload_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "request_params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_api_responses_duration_ms",
        ),
        sa.CheckConstraint(
            "http_status BETWEEN 100 AND 599",
            name="ck_api_responses_http_status",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["audit.ingestion_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="raw",
    )

    op.create_index(
        "ix_api_responses_run_id",
        "api_responses",
        ["ingestion_run_id"],
        schema="raw",
    )
    op.create_index(
        "ix_api_responses_received_at",
        "api_responses",
        ["received_at"],
        schema="raw",
    )
    op.create_index(
        "ix_api_responses_payload_hash",
        "api_responses",
        ["payload_hash"],
        schema="raw",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_api_responses_payload_hash",
        table_name="api_responses",
        schema="raw",
    )
    op.drop_index(
        "ix_api_responses_received_at",
        table_name="api_responses",
        schema="raw",
    )
    op.drop_index(
        "ix_api_responses_run_id",
        table_name="api_responses",
        schema="raw",
    )
    op.drop_table(
        "api_responses",
        schema="raw",
    )

    op.drop_index(
        "ix_ingestion_runs_status",
        table_name="ingestion_runs",
        schema="audit",
    )
    op.drop_index(
        "ix_ingestion_runs_source_started_at",
        table_name="ingestion_runs",
        schema="audit",
    )
    op.drop_table(
        "ingestion_runs",
        schema="audit",
    )
