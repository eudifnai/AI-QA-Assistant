"""Add WebSocket sequences, heartbeat, reconnect, and assertions.

Revision ID: 20260816_0015
Revises: 20260816_0014
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0015"
down_revision: str | None = "20260816_0014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("websocket_executions") as batch:
        batch.add_column(
            sa.Column("additional_messages_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("receive_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("ping_interval_seconds", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("max_reconnect_attempts", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("responses_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("assertions_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("assertion_results_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("websocket_executions") as batch:
        batch.drop_column("attempt_count")
        batch.drop_column("assertion_results_json")
        batch.drop_column("assertions_json")
        batch.drop_column("responses_json")
        batch.drop_column("max_reconnect_attempts")
        batch.drop_column("ping_interval_seconds")
        batch.drop_column("receive_count")
        batch.drop_column("additional_messages_json")
