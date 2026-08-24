"""Create singleton application settings.

Revision ID: 20260809_0003
Revises: 20260804_0002
Create Date: 2026-08-09
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0003"
down_revision: str | None = "20260804_0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("theme", sa.String(length=16), nullable=False),
        sa.Column("model_mode", sa.String(length=16), nullable=False),
        sa.Column("model_provider", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("cloud_data_consent", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="ck_app_settings_singleton"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
