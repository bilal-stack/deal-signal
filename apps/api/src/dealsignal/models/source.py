"""Provenance: one row per field per source, with its confidence and evidence.

This is what lets the UI show "founded 1999, from the company website" instead of a
bare value, and what decides which source wins when they disagree.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import SourceName

if TYPE_CHECKING:
    from dealsignal.models.company import Company


class FieldValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One value for one field, from one source, with its evidence."""

    __tablename__ = "field_values"

    company_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSONB)
    source: Mapped[SourceName] = mapped_column(String(32))

    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    """0.0 to 1.0. Registries score highest, a guess from page text lowest."""

    evidence: Mapped[str | None] = mapped_column(Text)
    """A short quote from the page, so a user can check the claim themselves."""

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(back_populates="field_values")

    __table_args__ = (
        UniqueConstraint("company_id", "field", "source", name="uq_field_value_per_source"),
        Index("ix_field_values_field", "field"),
    )
