"""Improve reservation locking indexes.

Revision ID: 0003_reservation_constraints
Revises: 0002_lottery_status
Create Date: 2026-11-25
"""

from alembic import op


revision = "0003_reservation_constraints"
down_revision = "0002_lottery_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_reservations_customer_lottery_status",
        "reservations",
        ["customer_id", "lottery_id", "status"],
    )
    op.create_index(
        "ix_reservations_expires_status",
        "reservations",
        ["expires_at", "status"],
    )
    op.create_index(
        "ix_tickets_lottery_status_customer",
        "tickets",
        ["lottery_id", "status", "customer_id"],
    )
    op.create_index(
        "ix_reservation_items_ticket_reservation",
        "reservation_items",
        ["ticket_id", "reservation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reservation_items_ticket_reservation", "reservation_items")
    op.drop_index("ix_tickets_lottery_status_customer", "tickets")
    op.drop_index("ix_reservations_expires_status", "reservations")
    op.drop_index("ix_reservations_customer_lottery_status", "reservations")
