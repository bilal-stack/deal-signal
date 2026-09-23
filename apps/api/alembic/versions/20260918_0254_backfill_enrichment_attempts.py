"""backfill enrichment attempts

Companies enriched before attempts were recorded would otherwise say "no lookups
recorded" while showing a register match. Their successes are recovered from the
facts already stored. Failures from that time were never stored, so those
companies are simply retried by the next run.

Revision ID: d62591e51f33
Revises: 2dbc38494104
Create Date: 2026-09-18 02:54:52.817212+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d62591e51f33"
down_revision: str | None = "2dbc38494104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOMAIN_AGE = """
INSERT INTO enrichment_attempts (company_id, task, attempted_at, succeeded, message)
SELECT company_id, 'domain_age', max(observed_at), true,
       'Domain registered in ' || max(value #>> '{}') || '.'
FROM field_values
WHERE field = 'domain_registered_year'
GROUP BY company_id
ON CONFLICT DO NOTHING
"""

REGISTRY = """
INSERT INTO enrichment_attempts (company_id, task, attempted_at, succeeded, message)
SELECT c.id, 'registry', coalesce(max(fv.observed_at), now()), true,
       'Matched ' || c.legal_name || ' in the register.'
FROM companies c
LEFT JOIN field_values fv
  ON fv.company_id = c.id AND fv.source IN ('recherche_entreprises', 'companies_house')
WHERE c.legal_name IS NOT NULL
GROUP BY c.id, c.legal_name
ON CONFLICT DO NOTHING
"""

WEBSITE = """
INSERT INTO enrichment_attempts (company_id, task, attempted_at, succeeded, message)
SELECT c.id, 'website', coalesce(max(fv.observed_at), now()), true, 'Website read.'
FROM companies c
LEFT JOIN field_values fv ON fv.company_id = c.id AND fv.source = 'website'
WHERE c.summary IS NOT NULL
GROUP BY c.id
ON CONFLICT DO NOTHING
"""


def upgrade() -> None:
    # One statement per call: asyncpg prepares each one on its own.
    for statement in (DOMAIN_AGE, REGISTRY, WEBSITE):
        op.execute(statement)


def downgrade() -> None:
    # The rows are indistinguishable from later ones, and harmless to keep.
    pass
