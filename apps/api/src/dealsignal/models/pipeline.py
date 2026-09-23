"""The deal board: which companies are being worked, and how far along they are."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import PipelineStage


class PipelineItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One company on the board. A company appears at most once."""

    __tablename__ = "pipeline_items"

    company_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True,
    )
    stage: Mapped[PipelineStage] = mapped_column(String(16), default=PipelineStage.NEW, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    next_action_on: Mapped[date | None] = mapped_column(Date)
    """When to follow up. Optional: not every lead has a next step yet."""
