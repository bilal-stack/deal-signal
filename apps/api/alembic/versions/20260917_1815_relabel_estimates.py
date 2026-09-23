"""relabel estimates

Revision ID: 8de639d3abe4
Revises: fa80cc4892fb
Create Date: 2026-09-17 18:15:31.977980+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "8de639d3abe4"
down_revision: str | None = "fa80cc4892fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # These rows were labelled with a Census dataset we never actually read. They are
    # our own estimates, and the label now says so.
    op.execute("update field_values set source = 'estimate' where source = 'census_susb'")


def downgrade() -> None:
    op.execute("update field_values set source = 'census_susb' where source = 'estimate'")
