"""The do-not-contact list.

Companies, domains or addresses that must never be approached: someone asked us to
stop, they are a competitor, or another partner is already working them. Checked
before an export and before any outreach draft, so a request to be left alone is
honoured even if the lead looks good.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import SuppressionKind


class SuppressionEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One thing we will not contact."""

    __tablename__ = "suppression_entries"

    kind: Mapped[SuppressionKind] = mapped_column(String(16), index=True)
    value: Mapped[str] = mapped_column(String(320), index=True)
    """A domain, an email address, or a company id, depending on `kind`. Stored lowercase."""

    reason: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(postgresql.UUID(as_uuid=True))
    """Set when the entry was added from a company, for showing it in the UI."""

    __table_args__ = (UniqueConstraint("kind", "value", name="uq_suppression_entry"),)
