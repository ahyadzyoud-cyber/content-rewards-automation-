"""Validated campaign records; a provider name alone never proves eligibility."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

Platform = Literal["youtube", "instagram"]
Source = Literal["whop", "content_rewards", "vyro", "manual"]
NonNegativeMoney = Annotated[float, Field(ge=0, allow_inf_nan=False)]
NonEmptyText = Annotated[str, Field(min_length=1, max_length=4000)]


class Campaign(BaseModel):
    """A normalized, explicitly evidenced campaign snapshot.

    Verification flags describe evidence supplied by the operator or an authorized
    provider. They are never inferred from campaign names, domains, or geography.
    Empty country/platform lists and ``allows_new_accounts=None`` mean unknown.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
    title: NonEmptyText
    source: Source
    source_url: HttpUrl
    rate_per_1000_views_usd: NonNegativeMoney
    remaining_budget_usd: NonNegativeMoney
    competition_entries: Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)] | None = None
    eligible_countries: list[str] = Field(default_factory=list)
    eligibility_verified: bool = False
    eligibility_evidence: str = ""
    allowed_platforms: list[Platform] = Field(default_factory=list)
    allows_new_accounts: bool | None = None
    minimum_followers: Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)] = 0
    requirements: list[NonEmptyText] = Field(default_factory=list)
    requirements_verified: bool = False
    rights_verified: bool = False
    materials: list[NonEmptyText] = Field(default_factory=list)
    active: bool = True
    evidence_checked_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("source_url must use HTTPS")
        if value.username or value.password:
            raise ValueError("source_url must not contain credentials")
        return value

    @field_validator("eligible_countries")
    @classmethod
    def normalize_countries(cls, values: list[str]) -> list[str]:
        countries = []
        for value in values:
            country = value.strip().upper()
            if len(country) != 2 or not country.isascii() or not country.isalpha():
                raise ValueError("eligible_countries must contain two-letter country codes")
            if country not in countries:
                countries.append(country)
        return countries

    @field_validator("allowed_platforms")
    @classmethod
    def unique_platforms(cls, values: list[Platform]) -> list[Platform]:
        return list(dict.fromkeys(values))

    @field_validator("evidence_checked_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("evidence_checked_at must include a timezone")
        return value


class CampaignScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    score: Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)]
    selectable: bool
    blockers: list[str]
    breakdown: dict[str, float]
