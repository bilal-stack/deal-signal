"""The deal board."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from dealsignal.core.deps import SessionDep
from dealsignal.models.enums import PipelineStage
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.pipeline import PipelineRepository
from dealsignal.schemas.pipeline import PipelineAdd, PipelineBoard, PipelineCard, PipelinePatch
from dealsignal.services.pipeline import PipelineService, PipelineUpdate

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("", response_model=PipelineBoard)
async def get_board(session: SessionDep) -> PipelineBoard:
    rows = await PipelineRepository(session).board()
    return PipelineBoard(
        stages=list(PipelineStage),
        cards=[PipelineCard.build(item, company) for item, company in rows],
    )


@router.post("", response_model=PipelineCard)
async def add_to_pipeline(
    payload: PipelineAdd, session: SessionDep, response: Response
) -> PipelineCard:
    """201 when the company is newly added, 200 when it was already on the board."""
    item, created = await PipelineService(session).add(payload.company_id)
    await session.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK

    company = await CompanyRepository(session).get_or_raise(item.company_id)
    return PipelineCard.build(item, company)


@router.patch("/{item_id}", response_model=PipelineCard)
async def update_card(
    item_id: uuid.UUID, payload: PipelinePatch, session: SessionDep
) -> PipelineCard:
    change = PipelineUpdate(**payload.model_dump())
    item = await PipelineService(session).update(item_id, change)
    await session.commit()

    company = await CompanyRepository(session).get_or_raise(item.company_id)
    return PipelineCard.build(item, company)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_card(item_id: uuid.UUID, session: SessionDep) -> Response:
    await PipelineService(session).remove(item_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
