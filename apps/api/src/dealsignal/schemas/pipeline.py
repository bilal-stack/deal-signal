"""Pipeline board requests and responses."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import Field

from dealsignal.models.company import Company
from dealsignal.models.enums import PipelineStage
from dealsignal.models.pipeline import PipelineItem
from dealsignal.schemas.common import ApiModel
from dealsignal.services.pipeline import MAX_NOTES_CHARS


class PipelineAdd(ApiModel):
    company_id: uuid.UUID


class PipelinePatch(ApiModel):
    stage: PipelineStage | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES_CHARS)
    next_action_on: date | None = None
    clear_next_action: bool = False


class PipelineCard(ApiModel):
    """One card on the board."""

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    city: str | None
    country: str
    phone: str | None
    domain: str | None
    stage: PipelineStage
    notes: str | None
    next_action_on: date | None

    @classmethod
    def build(cls, item: PipelineItem, company: Company) -> PipelineCard:
        return cls(
            id=item.id,
            company_id=company.id,
            name=company.display_name,
            city=company.city,
            country=str(company.country),
            phone=company.phone_e164,
            domain=company.domain,
            stage=PipelineStage(item.stage),
            notes=item.notes,
            next_action_on=item.next_action_on,
        )


class PipelineBoard(ApiModel):
    """Stages in order, so the UI never has to know the sequence itself."""

    stages: list[PipelineStage]
    cards: list[PipelineCard]
