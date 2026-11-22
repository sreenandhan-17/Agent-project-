"""Reset every seeded agent's password without touching anything else (tickets, customers,
holidays, audit log). Idempotent: safe to re-run any time credentials need rotating.

Usage (from /backend):
  DEMO_AGENT_PASSWORD="<new password>" python -m scripts.reset_agent_passwords

Writes no secrets to logs: the password itself is never printed, logged, or included in any
exception message — only the count of agents updated and their emails.
"""

import os

from sqlalchemy import select

from app.auth import hash_password
from app.db import get_sessionmaker
from app.models import Agent


def main() -> None:
    password = os.environ.get("DEMO_AGENT_PASSWORD")
    if not password:
        raise SystemExit(
            "DEMO_AGENT_PASSWORD is not set. Pass it inline, the same way DATABASE_URL is "
            "passed for production operations — never commit it. Example: "
            'DEMO_AGENT_PASSWORD="..." python -m scripts.reset_agent_passwords'
        )

    pw_hash = hash_password(password)
    with get_sessionmaker()() as session, session.begin():
        agents = session.scalars(select(Agent)).all()
        for agent in agents:
            agent.password_hash = pw_hash
        emails = sorted(a.email for a in agents)

    print(f"Reset password for {len(emails)} agent(s):")
    for email in emails:
        print(f"  {email}")


if __name__ == "__main__":
    main()
