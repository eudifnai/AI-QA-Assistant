"""Add frozen Protobuf assets.

Revision ID: 20260816_0013
Revises: 20260816_0012
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0013"
down_revision: str | None = "20260816_0012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "proto_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=2048), nullable=False),
        sa.Column("path_key", sa.String(length=2048), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("descriptor_set", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_proto_assets_workspace_path",
        "proto_assets",
        ["workspace_id", "path_key"],
        unique=True,
    )
    op.create_index(
        "uq_proto_assets_workspace_hash",
        "proto_assets",
        ["workspace_id", "sha256"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_proto_assets_workspace_hash", table_name="proto_assets")
    op.drop_index("uq_proto_assets_workspace_path", table_name="proto_assets")
    op.drop_table("proto_assets")
