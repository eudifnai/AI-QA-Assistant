"""Create stable document chunks for source citations.

Revision ID: 20260811_0005
Revises: 20260810_0004
Create Date: 2026-08-11
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0005"
down_revision: str | None = "20260810_0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=False),
        sa.Column("source_end", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_document_chunks_version_ordinal",
        "document_chunks",
        ["version_id", "ordinal"],
        unique=True,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO document_chunks (
                id, version_id, ordinal, source_type, source_start, source_end,
                start_offset, end_offset, text
            )
            SELECT id, id, 1, 'document', 1, 1, 0, length(parsed_text), parsed_text
            FROM document_versions
            WHERE status = 'passed' AND parsed_text IS NOT NULL AND length(parsed_text) > 0
            """
        )
    )


def downgrade() -> None:
    op.drop_index("uq_document_chunks_version_ordinal", table_name="document_chunks")
    op.drop_table("document_chunks")
