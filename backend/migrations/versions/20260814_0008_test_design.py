"""Add issue review and test point tables.

Revision ID: 20260814_0008
Revises: 20260812_0007
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0008"
down_revision: str | None = "20260812_0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_issue_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["analysis_issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_issue_reviews_run", "analysis_issue_reviews", ["run_id"], unique=False
    )
    op.create_index(
        "uq_analysis_issue_reviews_issue", "analysis_issue_reviews", ["issue_id"], unique=True
    )
    op.create_table(
        "test_points",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_issue_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("test_type", sa.String(length=24), nullable=False),
        sa.Column("priority", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("automation_candidate", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_issue_id"], ["analysis_issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_test_points_run_created", "test_points", ["run_id", "created_at"], unique=False
    )
    op.create_index("uq_test_points_source_issue", "test_points", ["source_issue_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_test_points_source_issue", table_name="test_points")
    op.drop_index("ix_test_points_run_created", table_name="test_points")
    op.drop_table("test_points")
    op.drop_index("uq_analysis_issue_reviews_issue", table_name="analysis_issue_reviews")
    op.drop_index("ix_analysis_issue_reviews_run", table_name="analysis_issue_reviews")
    op.drop_table("analysis_issue_reviews")
