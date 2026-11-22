"""Triage: tickets.needs_triage, tickets.customer_impact, audit action TRIAGED (notes/15)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

customer_impact = pg.ENUM("CANNOT_WORK", "PARTIAL", "QUESTION", name="customer_impact")


def upgrade() -> None:
    customer_impact.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "tickets",
        sa.Column("needs_triage", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "tickets",
        sa.Column("customer_impact", pg.ENUM(name="customer_impact", create_type=False)),
    )
    # Partial index: the "Needs triage" list stays fast however many tickets are closed.
    op.create_index(
        "ix_tickets_needs_triage", "tickets", ["needs_triage"],
        postgresql_where=sa.text("needs_triage"),
    )
    # PG 12+ allows this inside the migration transaction (the value isn't used here).
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'TRIAGED'")


def downgrade() -> None:
    op.drop_index("ix_tickets_needs_triage", table_name="tickets")
    op.drop_column("tickets", "customer_impact")
    op.drop_column("tickets", "needs_triage")
    customer_impact.drop(op.get_bind(), checkfirst=True)
    # Postgres can't drop a single enum value. Rows may reference it (audit_events is
    # append-only), so 'TRIAGED' stays in audit_action after a downgrade.
