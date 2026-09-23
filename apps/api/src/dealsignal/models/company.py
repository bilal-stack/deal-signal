"""The merged company record: one row per real business."""

from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import Country, EmployeeBand

if TYPE_CHECKING:
    from dealsignal.models.person import Person
    from dealsignal.models.source import FieldValue


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A business, after every source has been merged into one record.

    Almost every column is nullable on purpose. A missing value is a fact about the
    world, not an error, and it lowers confidence rather than the score.
    """

    __tablename__ = "companies"

    display_name: Mapped[str] = mapped_column(String(255))
    legal_name: Mapped[str | None] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)

    domain: Mapped[str | None] = mapped_column(String(253), index=True)
    """The business's own website domain. Not unique: franchisees and a practice's
    dentists can share one, and matching, not a constraint, decides who is who."""
    website_url: Mapped[str | None] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(String(20), index=True)

    street: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[Country] = mapped_column(String(2), index=True)
    geo: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )

    industry_label: Mapped[str | None] = mapped_column(String(160))
    industry_code: Mapped[str | None] = mapped_column(String(16), index=True)
    industry_keys: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(40)), default=list, server_default="{}"
    )
    """Our industries this company was found under, e.g. ["hvac", "plumbing"].

    Searches filter on these, not on the official industry code: HVAC and plumbing
    share one code (238220), so filtering by code put every plumber in HVAC results."""

    founded_year: Mapped[int | None] = mapped_column()
    employee_band: Mapped[EmployeeBand | None] = mapped_column(String(16))
    employee_count: Mapped[int | None] = mapped_column()
    revenue_low: Mapped[int | None] = mapped_column()
    revenue_high: Mapped[int | None] = mapped_column()

    summary: Mapped[str | None] = mapped_column(Text)
    """One paragraph written by the website reader, grounded in quoted evidence."""

    field_values: Mapped[list[FieldValue]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    people: Mapped[list[Person]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_companies_name_trgm",
            "normalized_name",
            postgresql_using="gin",
            postgresql_ops={"normalized_name": "gin_trgm_ops"},
        ),
        Index("ix_companies_geo", "geo", postgresql_using="gist"),
        Index("ix_companies_country_industry", "country", "industry_code"),
        Index("ix_companies_industry_keys", "industry_keys", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Company {self.display_name!r} ({self.country})>"
