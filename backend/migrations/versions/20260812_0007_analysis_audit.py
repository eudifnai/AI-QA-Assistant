"""Add per-run analysis input and cloud confirmation audit fields.

Revision ID: 20260812_0007
Revises: 20260812_0006
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0007"
down_revision: str | None = "20260812_0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("input_chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("input_character_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("cloud_data_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE analysis_runs
        SET input_chunk_count = (
                SELECT COUNT(*)
                FROM document_chunks
                WHERE document_chunks.version_id = analysis_runs.version_id
            ),
            input_character_count = COALESCE((
                SELECT SUM(LENGTH(document_chunks.text))
                FROM document_chunks
                WHERE document_chunks.version_id = analysis_runs.version_id
            ), 0)
        """
    )


def downgrade() -> None:
    op.drop_column("analysis_runs", "cloud_data_confirmed_at")
    op.drop_column("analysis_runs", "input_character_count")
    op.drop_column("analysis_runs", "input_chunk_count")
