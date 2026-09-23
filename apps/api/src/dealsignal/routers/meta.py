"""Reference lists the UI needs, served from the one place they are defined."""

from __future__ import annotations

from fastapi import APIRouter

from dealsignal.schemas.common import ApiModel
from dealsignal.sources.industries import INDUSTRIES
from dealsignal.sources.regions import REGIONS

router = APIRouter(prefix="/meta", tags=["reference"])


class RegionOption(ApiModel):
    key: str
    label: str
    country: str


class IndustryOption(ApiModel):
    key: str
    label: str


class Meta(ApiModel):
    regions: list[RegionOption]
    industries: list[IndustryOption]


@router.get("", response_model=Meta)
async def get_meta() -> Meta:
    return Meta(
        regions=[
            RegionOption(key=region.key, label=region.label, country=str(region.country))
            for region in REGIONS.values()
        ],
        industries=[
            IndustryOption(key=industry.key, label=industry.label) for industry in INDUSTRIES
        ],
    )
