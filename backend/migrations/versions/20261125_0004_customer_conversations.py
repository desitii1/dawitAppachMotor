"""Add persistent customer support conversations.

Revision ID: 0004_customer_conversations
Revises: 0003_reservation_constraints
Create Date: 2026-11-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_customer_conversations"
down_revision = "0003_reservation_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "direction IN ('INBOUND','OUTBOUND')",
            name="ck_conversation_message_direction",
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_messages_customer_id",
        "conversation_messages",
        ["customer_id"],
    )
    op.create_index(
        "ix_conversation_messages_sent_at",
        "conversation_messages",
        ["sent_at"],
    )
    op.create_index(
        "ix_conversation_messages_customer_sent_at",
        "conversation_messages",
        ["customer_id", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_customer_sent_at", table_name="conversation_messages")
    op.drop_index("ix_conversation_messages_sent_at", table_name="conversation_messages")
    op.drop_index("ix_conversation_messages_customer_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")
