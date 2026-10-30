"""Evidence-gated publication checks; post-publication outcomes remain pending.

Completeness is an operator review of the full official brief, never an NLP or
provider-feed assertion. Mechanical checks inspect actual bytes/metadata;
content and human participation require separately reviewed, bound evidence.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

CATEGORIES = frozenset({"platform", "duration", "format", "aspect_ratio", "content", "title", "caption",
                        "hashtags", "mentions", "account", "deadline", "minimum_views", "livestream",
                        "submission", "rights", "disclosures"})
Status = Literal["verified", "not_applicable", "unknown", "unmet"]


def _https(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in {None, 443} or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Evidence requires an HTTPS source without credentials or query values") from None
    return value


class BriefRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    category: str
    stage: Literal["prepublication", "postpublication", "submission"] = "prepublication"
    status: Status = "unknown"
    statement: str = Field(min_length=1, max_length=4000)
    evidence_url: str | None = None
    evidence_note: str = Field(default="", max_length=4000)
    critical: StrictBool = True
    check: Literal["manual", "platform", "duration", "format", "aspect_ratio", "title_contains",
                   "caption_contains", "hashtags", "mentions"] = "manual"
    minimum: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)
    maximum: float | None = Field(default=None, gt=0, strict=True, allow_inf_nan=False)
    value: str | None = Field(default=None, min_length=1, max_length=100)
    values: list[str] | None = None

    @field_validator("category")
    @classmethod
    def known_category(cls, value):
        if value not in CATEGORIES:
            raise ValueError("Unknown publication requirement category")
        return value

    @field_validator("evidence_url")
    @classmethod
    def safe_evidence(cls, value):
        return _https(value) if value is not None else None

    @model_validator(mode="after")
    def evidenced_conclusion(self):
        if not self.statement.strip():
            raise ValueError("Requirements need a brief clause or reviewed absence")
        if self.status in {"verified", "not_applicable"} and (not self.evidence_url or not self.evidence_note.strip()):
            raise ValueError("Known and not-applicable requirements need explicit source evidence")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Requirement minimum cannot exceed maximum")
        if self.values is not None and any(not value.strip() or len(value) > 2000 for value in self.values):
            raise ValueError("Required text values must be meaningful bounded text")
        automatic = {"platform": {"platform"}, "duration": {"duration"}, "format": {"format"},
                     "aspect_ratio": {"aspect_ratio"}, "title": {"title_contains"},
                     "caption": {"caption_contains"}, "hashtags": {"hashtags"}, "mentions": {"mentions"},
                     "disclosures": {"caption_contains"}}
        if self.check != "manual" and self.check not in automatic.get(self.category, set()):
            raise ValueError("This requirement category cannot be satisfied by that automatic check")
        return self


class PublicationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    full_brief_text: str = Field(min_length=1, max_length=100_000)
    brief_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    official_source_url: str
    reviewed_at: AwareDatetime
    review_complete: StrictBool = False
    requirements: list[BriefRequirement] = Field(default_factory=list, max_length=300)

    _source = field_validator("official_source_url")(_https)

    @model_validator(mode="after")
    def exact_brief_and_unique_requirements(self):
        if hashlib.sha256(self.full_brief_text.encode()).hexdigest() != self.brief_sha256:
            raise ValueError("The reviewed full brief does not match its SHA256")
        if len({item.id for item in self.requirements}) != len(self.requirements):
            raise ValueError("Brief requirement IDs must be unique")
        return self


class RequirementProof(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status = "unknown"
    evidence_url: str
    note: str = Field(min_length=1, max_length=4000)

    _source = field_validator("evidence_url")(_https)

    @field_validator("note")
    @classmethod
    def meaningful_note(cls, value):
        if not value.strip():
            raise ValueError("Proof needs a reviewed conclusion")
        return value


class JobComplianceReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_at: AwareDatetime
    proofs: dict[str, RequirementProof]


def _fresh(value: datetime, now: datetime) -> bool:
    return now - timedelta(days=7) <= value <= now + timedelta(minutes=5)


def _mechanical(requirement: BriefRequirement, job: dict, media: dict | None) -> bool | None:
    """None means the configured check or measured fact remains unknown."""
    kind, value, values = requirement.check, requirement.value, requirement.values
    if kind == "platform":
        return job.get("platform") == value if value in {"youtube", "instagram"} else None
    if kind == "duration":
        duration = (media or {}).get("duration_seconds")
        if (type(duration) not in {float, int} or not math.isfinite(duration) or duration <= 0
                or requirement.minimum is None and requirement.maximum is None):
            return None
        return ((requirement.minimum is None or duration >= requirement.minimum)
                and (requirement.maximum is None or duration <= requirement.maximum))
    if kind == "aspect_ratio":
        width, height = (media or {}).get("width"), (media or {}).get("height")
        match = re.fullmatch(r"([1-9][0-9]{0,5}):([1-9][0-9]{0,5})", value or "")
        if not match or any(type(v) is not int or v <= 0 for v in (width, height)):
            return None
        return width * int(match[2]) == height * int(match[1])
    if kind == "format":
        measured = (media or {}).get("container_format")
        brand = (media or {}).get("container_brand")
        if value not in {"mp4", "mov"} or not isinstance(measured, str) or not isinstance(brand, str):
            return None
        # MP4 and MOV share a demuxer name; only its actual major brand can
        # distinguish them. Unknown containers/brands cannot establish format.
        family, brand = measured.split(","), brand.strip()
        actual = ("mov" if brand == "qt" and "mov" in family else
                  "mp4" if "mp4" in family and (brand in {"isom", "mp41", "mp42", "avc1"}
                                                 or re.fullmatch(r"iso[2-9]", brand)) else None)
        return actual == value if actual else None
    if kind in {"title_contains", "caption_contains", "hashtags", "mentions"}:
        text = job.get("title" if kind == "title_contains" else "caption")
        if not isinstance(text, str) or not values:
            return None
        if kind in {"hashtags", "mentions"}:
            token = r"#\w+" if kind == "hashtags" else r"@[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*"
            if any(not re.fullmatch(token, fragment) for fragment in values):
                return None
            end = r"(?!\w)" if kind == "hashtags" else r"(?![\w.])"
            return all(re.search(r"(?<![\w@#])" + re.escape(fragment) + end, text, re.I)
                       for fragment in values)
        return all(fragment in text for fragment in values)
    return None


def compliance_report(campaign, job: dict, media: dict | None, *, binding_digest: str,
                      now: datetime | None = None) -> dict:
    """Assess publication readiness without approving, publishing or paying."""
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Compliance review clock must include a timezone")
    blockers, checks, pending = [], [], []
    spec = campaign.get("publication_spec") if isinstance(campaign, dict) else campaign.publication_spec
    if spec is None:
        return {"blockers": ["Full official brief and mandatory requirement inventory have not been reviewed"],
                "checks": [], "pending_postpublication": [], "compliant": False}
    spec = PublicationSpec.model_validate(spec)
    if not spec.review_complete or not _fresh(spec.reviewed_at, clock):
        blockers.append("Full official brief review is incomplete, stale or future-dated")
    if not CATEGORIES <= {item.category for item in spec.requirements if item.critical}:
        blockers.append("Mandatory requirement categories need explicit review, including any documented absence")
    before = {item.category for item in spec.requirements if item.critical and item.stage == "prepublication"}
    if not CATEGORIES - {"minimum_views", "submission"} <= before:
        blockers.append("Critical media, content, rights and workflow prerequisites must be covered before publication")
    try:
        review = JobComplianceReview.model_validate(job.get("compliance_review"))
        bound = review.digest == binding_digest and _fresh(review.reviewed_at, clock)
        if set(review.proofs) - {item.id for item in spec.requirements}:
            blockers.append("Compliance proof references an unknown brief requirement")
    except ValueError:
        review, bound = None, False
    for item in spec.requirements:
        state = item.status
        if state in {"unknown", "unmet"}:
            passed = False
        elif state == "not_applicable":
            passed = True
        elif item.category == "minimum_views" and item.stage == "prepublication":
            passed, state = False, "unknown"
        elif item.stage != "prepublication":
            pending.append({"id": item.id, "category": item.category, "stage": item.stage,
                            "status": "pending", "statement": item.statement})
            checks.append({"id": item.id, "status": "pending", "stage": item.stage})
            continue
        elif (item.critical and item.category in {"platform", "duration", "format", "aspect_ratio"}
              and item.check != item.category):
            passed, state = False, "unknown"
        elif item.check == "manual":
            proof = review.proofs.get(item.id) if review and bound else None
            passed = bool(proof and proof.status == "verified")
            state = "verified" if passed else "unknown"
        else:
            result = _mechanical(item, job, media)
            passed = result is True
            state = "verified" if passed else "unknown" if result is None else "unmet"
        checks.append({"id": item.id, "status": state, "stage": item.stage})
        if item.critical and not passed:
            blockers.append("Critical brief requirement " + item.id + " is " + state)
    return {"blockers": blockers, "checks": checks, "pending_postpublication": pending,
            "compliant": not blockers}
