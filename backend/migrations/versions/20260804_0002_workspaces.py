"""Create workspace records.

Revision ID: 20260804_0002
Revises: 20260801_0001
Create Date: 2026-08-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0002"
down_revision: str | None = "20260801_0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("name_key", sa.String(length=80), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("path_key", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_name_key", "workspaces", ["name_key"], unique=True)
    op.create_index("ix_workspaces_path_key", "workspaces", ["path_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_workspaces_path_key", table_name="workspaces")
    op.drop_index("ix_workspaces_name_key", table_name="workspaces")
    op.drop_table("workspaces")
