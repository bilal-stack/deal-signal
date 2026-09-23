"""Buy Box endpoints: save what you want to buy, then search with it."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Response, status

from dealsignal.core.deps import SessionDep
from dealsignal.models.buy_box import BuyBox
from dealsignal.repositories.buy_box import BuyBoxRepository
from dealsignal.schemas.buy_box import BuyBoxCreate, BuyBoxRead
from dealsignal.schemas.search import SearchRead
from dealsignal.services.buy_boxes import build_buy_box
from dealsignal.services.export import LeadExport, filename_for, to_csv, to_xlsx
from dealsignal.services.search import SearchService

router = APIRouter(prefix="/buy-boxes", tags=["buy boxes"])

MAX_LISTED = 100


@router.post("", response_model=BuyBoxRead, status_code=status.HTTP_201_CREATED)
async def create_buy_box(payload: BuyBoxCreate, session: SessionDep) -> BuyBox:
    """Save acquisition criteria for reuse."""
    buy_box = build_buy_box(payload)
    BuyBoxRepository(session).add(buy_box)
    await session.commit()
    return buy_box


@router.get("", response_model=list[BuyBoxRead])
async def list_buy_boxes(session: SessionDep) -> list[BuyBox]:
    """Saved Buy Boxes, newest first, for picking one to run again."""
    return await BuyBoxRepository(session).recent(limit=MAX_LISTED)


@router.post("/{buy_box_id}/search", response_model=SearchRead)
async def run_search(buy_box_id: uuid.UUID, session: SessionDep) -> SearchRead:
    """Score every stored company against this Buy Box, best first."""
    buy_box = await BuyBoxRepository(session).get_or_raise(buy_box_id)
    outcome = await SearchService(session).run(buy_box)
    await session.commit()  # the scores are saved as part of the search
    return SearchRead.from_outcome(outcome)


CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/{buy_box_id}/export")
async def export_results(
    buy_box_id: uuid.UUID,
    session: SessionDep,
    file_format: Literal["csv", "xlsx"] = Query(default="csv", alias="format"),
) -> Response:
    """Download the scored results, reasons included, for a CRM or a spreadsheet."""
    buy_box = await BuyBoxRepository(session).get_or_raise(buy_box_id)
    rows = await LeadExport(session).rows(buy_box)

    body = to_csv(rows) if file_format == "csv" else to_xlsx(rows)
    filename = filename_for(buy_box.name, file_format)
    return Response(
        content=body,
        media_type=CONTENT_TYPES[file_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
