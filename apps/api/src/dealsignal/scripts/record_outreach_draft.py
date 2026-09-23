"""Draft one outreach message with Claude, and keep the reply for tests.

    python -m dealsignal.scripts.record_outreach_draft --company <id> [--buy-box <id>]

Exactly one Claude call, never retried. The draft is written the way the API writes
it, from the facts DealSignal holds, and the reply is saved with those facts to
tests/fixtures/claude/outreach_draft.json. Nothing is sent to anyone.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from dealsignal.ai.outreach import OutreachWriter
from dealsignal.core.config import get_settings
from dealsignal.core.errors import DealSignalError
from dealsignal.core.logging import configure_logging
from dealsignal.db.session import dispose_engine, init_engine, session_scope
from dealsignal.repositories.buy_box import BuyBoxRepository
from dealsignal.scripts.claude_recording import (
    ExchangeRecorder,
    recording_client,
    request_summary,
    save_fixture,
)
from dealsignal.services.outreach import DraftResult, OutreachService, SenderProfile

DEFAULT_SENDER = SenderProfile(
    name="Alex Morgan",
    background=(
        "I run a small search fund and want to buy one established HVAC business in "
        "North Texas, keep its team and its name, and run it for the long term."
    ),
)


async def record(company_id: uuid.UUID, buy_box_id: uuid.UUID | None, sender: SenderProfile) -> int:
    settings = get_settings()
    configure_logging(settings)
    recorder = ExchangeRecorder()
    client = recording_client(settings, recorder)

    init_engine(settings)
    result: DraftResult | None = None
    try:
        async with session_scope() as session:
            buy_box = (
                await BuyBoxRepository(session).get_or_raise(buy_box_id) if buy_box_id else None
            )
            service = OutreachService(session, lambda: OutreachWriter(settings, client=client))
            result = await service.draft(company_id, sender, buy_box)
    except DealSignalError as error:
        print(error.message, file=sys.stderr)  # noqa: T201
    finally:
        await client.close()
        await dispose_engine()

    exchange = recorder.only_success()
    if result is None or exchange is None:
        return 1
    print(f"\nSubject: {result.draft.subject}\n\n{result.draft.body}\n")  # noqa: T201
    request, response = exchange
    save_fixture(
        "outreach_draft",
        script="record_outreach_draft.py",
        response=response,
        company=result.company_name,
        sender=sender.model_dump(),
        facts_used=result.facts_used,
        request=request_summary(request),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one real outreach draft for tests.")
    parser.add_argument("--company", type=uuid.UUID, required=True)
    parser.add_argument("--buy-box", type=uuid.UUID, default=None)
    parser.add_argument("--sender-name", default=DEFAULT_SENDER.name)
    parser.add_argument("--sender-background", default=DEFAULT_SENDER.background)
    args = parser.parse_args(argv)
    sender = SenderProfile(name=args.sender_name, background=args.sender_background)
    return asyncio.run(record(args.company, args.buy_box, sender))


if __name__ == "__main__":
    raise SystemExit(main())
