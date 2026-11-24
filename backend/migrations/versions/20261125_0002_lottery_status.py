"""Add lottery status constraint.

Revision ID: 0002_lottery_status
Revises: 0001_initial
Create Date: 2026-11-25
"""

from alembic import op


revision = "0002_lottery_status"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_lottery_status",
        "lotteries",
        "status IN ('DRAFT','ACTIVE','PAUSED','CLOSED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_lottery_status", "lotteries", type_="check")
