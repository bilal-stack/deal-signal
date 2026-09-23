"""Drafting outreach, and the list of companies we will not contact."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from dealsignal.ai.outreach import OutreachWriter
from dealsignal.core.deps import SessionDep, SettingsDep
from dealsignal.repositories.buy_box import BuyBoxRepository
from dealsignal.schemas.outreach import (
    DraftRead,
    DraftRequest,
    SuppressionAdd,
    SuppressionRead,
)
from dealsignal.services.outreach import OutreachService, SenderProfile
from dealsignal.services.suppression import SuppressionService

router = APIRouter(tags=["outreach"])


@router.post("/outreach/drafts", response_model=DraftRead)
async def draft_outreach(
    payload: DraftRequest, session: SessionDep, settings: SettingsDep
) -> DraftRead:
    """Write a first message, using what we already know about the company."""
    buy_box = (
        await BuyBoxRepository(session).get_or_raise(payload.buy_box_id)
        if payload.buy_box_id
        else None
    )
    result = await OutreachService(session, lambda: OutreachWriter(settings)).draft(
        payload.company_id,
        SenderProfile(name=payload.sender.name, background=payload.sender.background),
        buy_box,
    )
    return DraftRead(
        company_id=result.company_id,
        company_name=result.company_name,
        subject=result.draft.subject,
        body=result.draft.body,
        opening_fact=result.draft.opening_fact,
        follow_up=result.draft.follow_up,
        facts_used=result.facts_used,
    )


@router.get("/suppression", response_model=list[SuppressionRead])
async def list_suppression(session: SessionDep) -> list[SuppressionRead]:
    entries = await SuppressionService(session).entries()
    return [SuppressionRead.model_validate(entry) for entry in entries]


@router.post("/suppression", response_model=SuppressionRead, status_code=status.HTTP_201_CREATED)
async def add_suppression(payload: SuppressionAdd, session: SessionDep) -> SuppressionRead:
    """Never contact this company, or anyone at this website domain."""
    entry = await SuppressionService(session).block(payload.kind, payload.value, payload.reason)
    await session.commit()
    return SuppressionRead.model_validate(entry)


@router.delete("/suppression/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_suppression(entry_id: uuid.UUID, session: SessionDep) -> Response:
    await SuppressionService(session).unblock(entry_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
