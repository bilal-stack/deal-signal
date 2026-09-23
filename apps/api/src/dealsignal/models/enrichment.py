"""What each enrichment job last tried for a company, and how it went.

Jobs pick the companies they have not done yet. Some can never be done: the
registry publishes no date, the register has no match, the website blocks robots.
Without a record of attempts those are picked first on every run, and once there
are enough of them a job does no new work at all. The same record lets the company
panel say why a field is still empty.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from dealsignal.db.base import Base
from dealsignal.models.enums import EnrichmentTask


class EnrichmentAttempt(Base):
    """The latest attempt at one task for one company. Older attempts are replaced."""

    __tablename__ = "enrichment_attempts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task: Mapped[EnrichmentTask] = mapped_column(String(32), primary_key=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    succeeded: Mapped[bool]
    message: Mapped[str] = mapped_column(Text)
    """The outcome in words a user can read, shown in the company panel."""
