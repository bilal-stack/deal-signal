"""drop unused columns

Removes storage nothing ever wrote to: raw source records (field-level provenance
replaced them), an embedding column for a search that was never built, and contact
fields for people that no source provides.

Revision ID: 1e88cc75193e
Revises: d12ef2a10a6e
Create Date: 2026-09-21 19:21:20.362762+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1e88cc75193e"
down_revision: str | None = "d12ef2a10a6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    op.drop_index(op.f("ix_company_sources_company_id"), table_name="company_sources")
    op.drop_table("company_sources")
    op.drop_column("companies", "embedding")
    for column in ("email", "email_status", "phone_e164", "linkedin_url"):
        op.drop_column("people", column)


def downgrade() -> None:
    op.add_column("people", sa.Column("linkedin_url", sa.Text(), nullable=True))
    op.add_column("people", sa.Column("phone_e164", sa.String(length=20), nullable=True))
    op.add_column(
        "people",
        sa.Column("email_status", sa.String(length=24), nullable=False, server_default="unknown"),
    )
    op.add_column("people", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column(
        "companies",
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )
    op.create_table(
        "company_sources",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "source", "external_id", name="uq_company_source"),
    )
    op.create_index(
        op.f("ix_company_sources_company_id"), "company_sources", ["company_id"], unique=False
    )
