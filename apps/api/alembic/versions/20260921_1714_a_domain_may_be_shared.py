"""a domain may be shared

"One company per domain" is false: franchisees share their brand's website and a
practice lists each dentist separately. With the constraint, the second franchisee
could not even be stored. Matching now decides, and sends doubtful pairs to review.

Revision ID: d12ef2a10a6e
Revises: d62591e51f33
Create Date: 2026-09-21 17:14:15.672282+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d12ef2a10a6e"
down_revision: str | None = "d62591e51f33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("companies_domain_key"), "companies", type_="unique")
    op.create_index(op.f("ix_companies_domain"), "companies", ["domain"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_companies_domain"), table_name="companies")
    op.create_unique_constraint(op.f("companies_domain_key"), "companies", ["domain"])
