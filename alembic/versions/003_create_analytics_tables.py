"""create analytics tables (conversations, messages, service_inquiries)

Revision ID: 003
Revises: 002
Create Date: 2026-07-03

Tables defined in src/db/models.py for conversation tracking and owner dashboard.
Not yet wired into the bot flow — schema is created here so it is ready for the
persistent-state migration planned for pre-PRE.
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("chatwoot_conversation_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("customer_phone", sa.String(50), nullable=True),
        sa.Column("language", sa.String(2), server_default="es"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("current_step", sa.String(50), nullable=True),
        sa.Column("selected_service", sa.String(100), nullable=True),
        sa.Column("is_certified", sa.Boolean, nullable=True),
        sa.Column("location", sa.String(20), nullable=True),
        sa.Column("is_colombian", sa.Boolean, nullable=True),
        sa.Column("booking_link_sent", sa.Boolean, server_default=sa.false()),
        sa.Column("escalated", sa.Boolean, server_default=sa.false()),
        sa.Column("escalation_reason", sa.Text, nullable=True),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(50), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "service_inquiries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(50), nullable=False, index=True),
        sa.Column("service_key", sa.String(100), nullable=False),
        sa.Column("led_to_booking", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("service_inquiries")
    op.drop_table("messages")
    op.drop_table("conversations")
