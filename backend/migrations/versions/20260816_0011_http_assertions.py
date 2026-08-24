"""Add HTTP assertions, retries, and execution events.

Revision ID: 20260816_0011
Revises: 20260815_0010
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0011"
down_revision: str | None = "20260815_0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "http_executions",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "http_executions",
        sa.Column("assertions_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "http_executions",
        sa.Column("assertion_results_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "http_execution_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["http_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_http_execution_events_run_ordinal",
        "http_execution_events",
        ["run_id", "ordinal"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_http_execution_events_run_ordinal", table_name="http_execution_events")
    op.drop_table("http_execution_events")
    op.drop_column("http_executions", "assertion_results_json")
    op.drop_column("http_executions", "assertions_json")
    op.drop_column("http_executions", "max_attempts")
