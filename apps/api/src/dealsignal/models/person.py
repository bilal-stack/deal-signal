"""Owners and decision-makers."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import SourceName

if TYPE_CHECKING:
    from dealsignal.models.company import Company


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named person at a company.

    `birth_year` is the year only, never a full date, even where a registry
    publishes the month as well.
    """

    __tablename__ = "people"

    company_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str | None] = mapped_column(String(120))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_company: Mapped[bool] = mapped_column(Boolean, default=False)
    """True for a corporate director such as a holding company."""
    birth_year: Mapped[int | None] = mapped_column()
    appointed_year: Mapped[int | None] = mapped_column()

    source: Mapped[SourceName] = mapped_column(String(32))

    company: Mapped[Company] = relationship(back_populates="people")

    def __repr__(self) -> str:
        return f"<Person {self.full_name!r} owner={self.is_owner}>"
