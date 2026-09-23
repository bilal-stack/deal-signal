"""Match stored companies to their national company register.

python -m dealsignal.scripts.registry --country FR --limit 25
"""

from __future__ import annotations

import argparse

from dealsignal.models.enums import Country
from dealsignal.scripts.run_job import run
from dealsignal.workers.jobs import lookup_registry

DEFAULT_LIMIT = 25


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Look companies up in a public register.")
    parser.add_argument("--country", required=True, choices=[str(country) for country in Country])
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)
    return run(lookup_registry, country=args.country, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
