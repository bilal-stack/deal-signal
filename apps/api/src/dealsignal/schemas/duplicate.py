"""Review queue responses."""

from __future__ import annotations

import uuid

from dealsignal.models.company import Company
from dealsignal.schemas.common import ApiModel
from dealsignal.services.duplicate_resolution import Resolution


class DuplicateSide(ApiModel):
    """One of the two companies, with the fields a reviewer compares."""

    id: uuid.UUID
    name: str
    domain: str | None
    phone: str | None
    address: str | None
    founded_year: int | None

    @classmethod
    def from_company(cls, company: Company) -> DuplicateSide:
        address = ", ".join(
            part for part in (company.street, company.city, company.postal_code) if part
        )
        return cls(
            id=company.id,
            name=company.display_name,
            domain=company.domain,
            phone=company.phone_e164,
            address=address or None,
            founded_year=company.founded_year,
        )


class DuplicatePair(ApiModel):
    id: uuid.UUID
    similarity: float
    reason: str | None
    left: DuplicateSide
    right: DuplicateSide


class ResolveResult(ApiModel):
    id: uuid.UUID
    status: str
    message: str
    company_id: uuid.UUID | None = None

    @classmethod
    def from_resolution(cls, resolution: Resolution) -> ResolveResult:
        return cls(
            id=resolution.candidate_id,
            status=str(resolution.status),
            message=resolution.message,
            company_id=resolution.company_id,
        )
