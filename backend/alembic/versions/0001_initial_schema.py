"""Initial schema + append-only audit_events trigger

Revision ID: 0001
Revises:
Create Date: 2026-11-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> pg.ENUM:
    return pg.ENUM(*values, name=name, create_type=False)


agent_role = _enum("agent_role", "AGENT", "ADMIN")
ticket_status = _enum(
    "ticket_status", "NEW", "OPEN", "WAITING_ON_CUSTOMER", "RESOLVED", "CLOSED", "REOPENED"
)
ticket_priority = _enum("ticket_priority", "URGENT", "MEDIUM", "LOW")
author_type = _enum("author_type", "AGENT", "CUSTOMER", "SYSTEM")
message_visibility = _enum("message_visibility", "PUBLIC", "INTERNAL")
audit_action = _enum(
    "audit_action",
    "TICKET_CREATED", "CLAIMED", "STATUS_CHANGED", "PRIORITY_CHANGED", "REPLY_SENT",
    "NOTE_ADDED", "CUSTOMER_REPLIED", "SLA_PAUSED", "SLA_RESUMED", "AUTO_CLOSED",
    "REOPENED", "FOLLOW_UP_CREATED",
)
ALL_ENUMS = [agent_role, ticket_status, ticket_priority, author_type, message_visibility, audit_action]

TSTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    bind = op.get_bind()
    for e in ALL_ENUMS:
        e.create(bind, checkfirst=True)

    op.execute("CREATE SEQUENCE ticket_number_seq START WITH 1001")

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("role", agent_role, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TSTZ, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("phone", sa.String(32)),
        sa.Column("company", sa.String(120)),
        sa.Column("created_at", TSTZ, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "number", sa.String(20), nullable=False, unique=True,
            server_default=sa.text("'FD-' || nextval('ticket_number_seq')"),
        ),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("agents.id")),
        sa.Column("status", ticket_status, nullable=False),
        sa.Column("priority", ticket_priority, nullable=False),
        sa.Column("created_at", TSTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("first_response_at", TSTZ),
        sa.Column("first_response_due_at", TSTZ),
        sa.Column("resolution_due_at", TSTZ),
        sa.Column("paused_at", TSTZ),
        sa.Column("paused_minutes", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_customer_reply_at", TSTZ),
        sa.Column("resolved_at", TSTZ),
        sa.Column("closed_at", TSTZ),
        sa.Column("reopen_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("parent_ticket_id", sa.Integer, sa.ForeignKey("tickets.id")),
        sa.Column("public_token", sa.String(64), nullable=False, unique=True),
    )
    op.execute("ALTER SEQUENCE ticket_number_seq OWNED BY tickets.number")
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_resolution_due_at", "tickets", ["resolution_due_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_id", sa.Integer, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("author_type", author_type, nullable=False),
        sa.Column("author_agent_id", sa.Integer, sa.ForeignKey("agents.id")),
        sa.Column("author_customer_id", sa.Integer, sa.ForeignKey("customers.id")),
        sa.Column("visibility", message_visibility, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", TSTZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_ticket_id", "messages", ["ticket_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_id", sa.Integer, sa.ForeignKey("tickets.id")),
        sa.Column("actor_type", author_type, nullable=False),
        sa.Column("actor_id", sa.Integer),
        sa.Column("action", audit_action, nullable=False),
        sa.Column("field", sa.String(64)),
        sa.Column("old_value", pg.JSONB),
        sa.Column("new_value", pg.JSONB),
        sa.Column("created_at", TSTZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_ticket_id", "audit_events", ["ticket_id"])

    op.create_table(
        "holidays",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
    )

    # --- INC-0318: audit_events is append-only -------------------------------
    op.execute(
        """
        CREATE FUNCTION audit_events_block_changes() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_block_changes();
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION audit_events_block_changes();
        """
    )
    # Server timestamp only: ignore any client-supplied created_at.
    op.execute(
        """
        CREATE FUNCTION audit_events_server_timestamp() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.created_at := clock_timestamp();
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_set_created_at
        BEFORE INSERT ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_server_timestamp();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_events")  # DROP is not blocked by the triggers
    op.execute("DROP FUNCTION IF EXISTS audit_events_block_changes()")
    op.execute("DROP FUNCTION IF EXISTS audit_events_server_timestamp()")
    op.drop_table("holidays")
    op.drop_table("messages")
    op.drop_table("tickets")
    op.drop_table("customers")
    op.drop_table("agents")
    bind = op.get_bind()
    for e in reversed(ALL_ENUMS):
        e.drop(bind, checkfirst=True)
