"""Load companies for one region and industry from Overture Maps.

python -m dealsignal.scripts.seed --region dallas --industry hvac --limit 150
"""

from __future__ import annotations

import argparse

from dealsignal.scripts.run_job import run
from dealsignal.sources.regions import REGIONS
from dealsignal.workers.jobs import seed_region

DEFAULT_LIMIT = 150


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load a region and industry from open data.")
    parser.add_argument("--region", required=True, choices=sorted(REGIONS))
    parser.add_argument("--industry", required=True)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)
    return run(seed_region, region=args.region, industry=args.industry, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
