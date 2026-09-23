"""Read company websites with Claude, and record when their domains were registered.

    python -m dealsignal.scripts.enrich websites --limit 5
    python -m dealsignal.scripts.enrich domain-age --limit 100

Each website is one Claude call, billed to the configured key, so the batch is small
by default.
"""

from __future__ import annotations

import argparse

from dealsignal.schemas.jobs import DEFAULT_WEBSITE_READS, MAX_WEBSITE_READS
from dealsignal.scripts.run_job import run
from dealsignal.workers.jobs import check_domain_age, read_websites

DEFAULT_DOMAIN_AGE_LOOKUPS = 50


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrich stored companies.")
    parser.add_argument("what", choices=("websites", "domain-age"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if args.what == "websites":
        limit = min(args.limit or DEFAULT_WEBSITE_READS, MAX_WEBSITE_READS)
        return run(read_websites, limit=limit)
    return run(check_domain_age, limit=args.limit or DEFAULT_DOMAIN_AGE_LOOKUPS)


if __name__ == "__main__":
    raise SystemExit(main())
