"""Saved acquisition criteria, and the scores computed against them."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dealsignal.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from dealsignal.models.enums import BuyBoxMode

DEFAULT_RADIUS_KM = 50


class BuyBox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What the user wants to buy. Filled in once, reused by every search."""

    __tablename__ = "buy_boxes"

    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[BuyBoxMode] = mapped_column(String(16), default=BuyBoxMode.ACQUISITION)
    industries: Mapped[list[str]] = mapped_column(ARRAY(String(120)), default=list)
    countries: Mapped[list[str]] = mapped_column(ARRAY(String(2)), default=list)
    city: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    radius_km: Mapped[int] = mapped_column(Integer, default=DEFAULT_RADIUS_KM)

    revenue_min: Mapped[int | None] = mapped_column()
    revenue_max: Mapped[int | None] = mapped_column()
    employees_min: Mapped[int | None] = mapped_column()
    employees_max: Mapped[int | None] = mapped_column()

    exclude_pe_owned: Mapped[bool] = mapped_column(default=True)

    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    """Per-signal weight overrides. Empty means the defaults in `scoring/`."""

    def __repr__(self) -> str:
        return f"<BuyBox {self.name!r}>"


class Score(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One company scored against one Buy Box, with the reasons kept.

    `reasons` is a list of {signal, points, max_points, text, evidence}, which is
    exactly what the UI shows, so a score can never appear without its explanation.
    """

    __tablename__ = "scores"

    company_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    buy_box_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("buy_boxes.id", ondelete="CASCADE"), index=True
    )

    score: Mapped[float | None] = mapped_column(Float)
    """None when no signal had data. Zero would claim a judgement we have not made."""

    confidence: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_scores_buy_box_rank", "buy_box_id", "score"),
        Index("ix_scores_company_buy_box", "company_id", "buy_box_id", unique=True),
    )
