"""Add HTTP environments and execution history.

Revision ID: 20260815_0010
Revises: 20260814_0009
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0010"
down_revision: str | None = "20260814_0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "http_environments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("variables_json", sa.Text(), nullable=False),
        sa.Column("secret_names_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_http_environments_workspace_name",
        "http_environments",
        ["workspace_id", "name_key"],
        unique=True,
    )
    op.create_table(
        "http_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("environment_id", sa.String(length=36), nullable=True),
        sa.Column("environment_name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("variables_json", sa.Text(), nullable=False),
        sa.Column("secret_names_json", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path_template", sa.String(length=4096), nullable=False),
        sa.Column("headers_template_json", sa.Text(), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_headers_json", sa.Text(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_body_encoding", sa.String(length=8), nullable=True),
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
        "ix_http_executions_workspace_created",
        "http_executions",
        ["workspace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_http_executions_workspace_created", table_name="http_executions")
    op.drop_table("http_executions")
    op.drop_index("uq_http_environments_workspace_name", table_name="http_environments")
    op.drop_table("http_environments")
