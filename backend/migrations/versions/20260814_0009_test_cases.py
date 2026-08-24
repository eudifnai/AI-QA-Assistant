"""Add structured test cases and steps.

Revision ID: 20260814_0009
Revises: 20260814_0008
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0009"
down_revision: str | None = "20260814_0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "test_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_test_point_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("preconditions_json", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=2), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("automation_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_test_point_id"], ["test_points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_test_cases_run_created", "test_cases", ["run_id", "created_at"], unique=False
    )
    op.create_index(
        "uq_test_cases_source_point", "test_cases", ["source_test_point_id"], unique=True
    )
    op.create_table(
        "test_case_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("test_case_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_test_case_steps_case_ordinal",
        "test_case_steps",
        ["test_case_id", "ordinal"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_test_case_steps_case_ordinal", table_name="test_case_steps")
    op.drop_table("test_case_steps")
    op.drop_index("uq_test_cases_source_point", table_name="test_cases")
    op.drop_index("ix_test_cases_run_created", table_name="test_cases")
    op.drop_table("test_cases")
