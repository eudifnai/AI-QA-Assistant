"""Add WebSocket executions and ordered events.

Revision ID: 20260816_0012
Revises: 20260816_0011
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0012"
down_revision: str | None = "20260816_0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "websocket_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("environment_id", sa.String(length=36), nullable=True),
        sa.Column("environment_name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("path_template", sa.Text(), nullable=False),
        sa.Column("headers_template_json", sa.Text(), nullable=False),
        sa.Column("variables_json", sa.Text(), nullable=False),
        sa.Column("secret_names_json", sa.Text(), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("response_message", sa.Text(), nullable=True),
        sa.Column("response_encoding", sa.String(length=16), nullable=True),
        sa.Column("response_size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["environment_id"], ["http_environments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_websocket_executions_workspace_created",
        "websocket_executions",
        ["workspace_id", "created_at"],
    )
    op.create_table(
        "websocket_execution_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["websocket_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_websocket_execution_events_run_ordinal",
        "websocket_execution_events",
        ["run_id", "ordinal"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_websocket_execution_events_run_ordinal",
        table_name="websocket_execution_events",
    )
    op.drop_table("websocket_execution_events")
    op.drop_index("ix_websocket_executions_workspace_created", table_name="websocket_executions")
    op.drop_table("websocket_executions")
