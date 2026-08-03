"""Create the initial migration baseline.

Revision ID: 20260801_0001
Revises:
Create Date: 2026-08-01
"""

revision: str = "20260801_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Establish the Alembic baseline without premature business tables."""


def downgrade() -> None:
    """Return to the pre-schema baseline."""
