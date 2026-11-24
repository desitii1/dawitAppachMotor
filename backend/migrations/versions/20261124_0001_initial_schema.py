"""Create the initial lottery platform schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_telegram_id", "customers", ["telegram_id"], unique=True)

    op.create_table(
        "lotteries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_number", sa.Integer(), nullable=False),
        sa.Column("end_number", sa.Integer(), nullable=False),
        sa.Column("ticket_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("reservation_duration_hours", sa.Integer(), nullable=False),
        sa.Column("max_numbers_per_customer", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_number >= 0", name="ck_lottery_start_nonnegative"),
        sa.CheckConstraint("end_number >= start_number", name="ck_lottery_range"),
        sa.CheckConstraint("ticket_price >= 0", name="ck_lottery_price"),
        sa.CheckConstraint("reservation_duration_hours > 0", name="ck_lottery_duration"),
        sa.CheckConstraint("max_numbers_per_customer > 0", name="ck_lottery_limit"),
    )

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lottery_id", sa.Integer(), sa.ForeignKey("lotteries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('AWAITING_PAYMENT','PAYMENT_SUBMITTED','APPROVED','REJECTED','EXPIRED','CANCELLED')",
            name="ck_reservation_status",
        ),
    )
    op.create_index("ix_reservations_reference", "reservations", ["reference"], unique=True)
    op.create_index("ix_reservations_customer_id", "reservations", ["customer_id"])
    op.create_index("ix_reservations_lottery_id", "reservations", ["lottery_id"])
    op.create_index("ix_reservations_status", "reservations", ["status"])

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lottery_id", sa.Integer(), sa.ForeignKey("lotteries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("lottery_id", "number", name="uq_ticket_lottery_number"),
        sa.CheckConstraint("status IN ('AVAILABLE','RESERVED','SOLD')", name="ck_ticket_status"),
    )
    op.create_index("ix_tickets_lottery_id", "tickets", ["lottery_id"])
    op.create_index("ix_tickets_number", "tickets", ["number"])
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "reservation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("reservation_id", "ticket_id", name="uq_reservation_ticket"),
    )
    op.create_index("ix_reservation_items_reservation_id", "reservation_items", ["reservation_id"])
    op.create_index("ix_reservation_items_ticket_id", "reservation_items", ["ticket_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("rejection_reason", sa.String(length=1000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("reservation_id", name="uq_payments_reservation_id"),
        sa.CheckConstraint("status IN ('AWAITING_PAYMENT','PAYMENT_SUBMITTED','APPROVED','REJECTED','EXPIRED')", name="ck_payment_status"),
    )
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "payment_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_attachments_payment_id", "payment_attachments", ["payment_id"])

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_activity_logs_customer_id", "activity_logs", ["customer_id"])
    op.create_index("ix_activity_logs_activity_type", "activity_logs", ["activity_type"])
    op.create_index("ix_activity_logs_created_at", "activity_logs", ["created_at"])

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("image_storage_key", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('QUEUED','PROCESSING','COMPLETED','FAILED')", name="ck_broadcast_status"),
    )

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broadcast_id", sa.Integer(), sa.ForeignKey("broadcasts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("delivery_status IN ('PENDING','SENT','FAILED')", name="ck_broadcast_delivery_status"),
    )
    op.create_index("ix_broadcast_deliveries_broadcast_id", "broadcast_deliveries", ["broadcast_id"])
    op.create_index("ix_broadcast_deliveries_customer_id", "broadcast_deliveries", ["customer_id"])


def downgrade() -> None:
    op.drop_table("broadcast_deliveries")
    op.drop_table("broadcasts")
    op.drop_table("activity_logs")
    op.drop_table("payment_attachments")
    op.drop_table("payments")
    op.drop_table("reservation_items")
    op.drop_table("tickets")
    op.drop_table("reservations")
    op.drop_table("lotteries")
    op.drop_table("customers")
    op.drop_table("admin_users")
