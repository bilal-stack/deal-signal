"""Possible duplicates waiting for a person to decide.

The matcher merges what it is sure about and refuses to guess at the rest. Those
uncertain pairs land here instead of being silently merged or silently dropped,
because both of those are ways to lose a company without telling anyone.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import DuplicateStatus


class DuplicateCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Two companies that might be the same business."""

    __tablename__ = "duplicate_candidates"

    company_a_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    company_b_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )
    """Cleared when the pair is merged: the second record no longer exists, but the
    decision to merge it is worth keeping."""
    similarity: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    """Why the matcher thought so, in the words the reviewer will read."""

    status: Mapped[DuplicateStatus] = mapped_column(
        String(16), default=DuplicateStatus.PENDING, index=True
    )

    __table_args__ = (UniqueConstraint("company_a_id", "company_b_id", name="uq_duplicate_pair"),)
