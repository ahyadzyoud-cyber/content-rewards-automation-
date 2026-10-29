"""Evidence-gated fixed-bounty assessment, separate from CPM campaigns.

API visibility, quoted rewards and available slots are observations. They do
not establish that this owner can earn, use materials, or automate publication.
Only separately reviewed, dated evidence can clear those gates. This module
never creates a Campaign, a publication job, a submission or an approval.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
)

MAX_EVIDENCE_AGE = timedelta(days=7)
FIXED_REWARD_MODEL = "fixed_reward_per_approved_submission"


class BountyEvidence(BaseModel):
    """An operator-reviewed fact; never infer this from imported provider text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirmed: StrictBool
    checked_at: AwareDatetime
    source_url: str = Field(min_length=1, max_length=2048)
    detail: str = Field(min_length=1, max_length=2000)

    @field_validator("source_url")
    @classmethod
    def https_reference(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise ValueError("Evidence must reference an HTTPS source") from None
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or port not in {None, 443} or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)):
            raise ValueError("Evidence must reference an HTTPS source without credentials or query values")
        return value

    @field_validator("detail")
    @classmethod
    def meaningful_detail(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidence requires a reviewed conclusion")
        return value.strip()


class BountyVerification(BaseModel):
    """Private owner/account-specific review, bound to one opportunity.

    Evidence fields are deliberately separate. A creator-country match in the
    API does not stand in for payout KYC, campaign admission, or rights. Import
    adapters must not instantiate this model from untrusted campaign fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    bounty_id: str = Field(pattern=r"^bnty_[A-Za-z0-9_-]{1,160}$")
    creator_country: str = Field(pattern=r"^[A-Z]{2}$")
    country_eligibility: BountyEvidence | None = None
    new_accounts: BountyEvidence | None = None
    minimum_followers: int | None = Field(default=None, ge=0, strict=True)
    payout_eligibility: BountyEvidence | None = None
    material_rights: BountyEvidence | None = None
    materials_available: BountyEvidence | None = None
    automation_permission: BountyEvidence | None = None
    requirements: BountyEvidence | None = None
    expires_at: AwareDatetime | None = None
    no_deadline: StrictBool = False
    platform_permission: BountyEvidence | None = None
    allowed_platforms: list[str] = Field(default_factory=list)
    competition: BountyEvidence | None = None
    competing_entries: int | None = Field(default=None, ge=0, strict=True)

    @field_validator("allowed_platforms")
    @classmethod
    def supported_platforms(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or not set(values) <= {"youtube", "instagram"}:
            raise ValueError("Use youtube and/or instagram once each")
        return values


def _fresh(evidence: BountyEvidence | None, now: datetime) -> bool:
    return bool(evidence is not None and evidence.confirmed
                and now - MAX_EVIDENCE_AGE <= evidence.checked_at <= now + timedelta(minutes=5))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def _report_fresh(value: object, now: datetime) -> bool:
    if not isinstance(value, str):
        return False
    try:
        checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return bool(checked.tzinfo is not None and checked.utcoffset() is not None
                and now - MAX_EVIDENCE_AGE <= checked <= now + timedelta(minutes=5))


def rank_whop_bounties(
    report: dict,
    verifications: Mapping[str, BountyVerification] | None = None,
    country: str = "JO",
    platforms: Iterable[str] = ("youtube", "instagram"),
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Return weakness-first assessments of fixed rewards; score verified work.

    Unknown eligibility prevents a selectable score. ``evidence_score`` is a
    partial research heuristic, not projected earnings or campaign admission.
    USD quoted net reward contributes 3 points, verified country/admission 2,
    separately verified competition 1.5, observed open capacity 2, and verified
    requirements/rights 1.5. Other currencies have no reward-size points because
    no exchange-rate evidence is available. Slots do not establish a cash
    budget: pending reservations and settlement rules require separate review.
    """
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if not isinstance(country, str) or len(country) != 2 or not country.isascii() or not country.isalpha():
        raise ValueError("country must be a two-letter creator residency code")
    country = country.upper()
    requested = set(platforms)
    if not requested or not requested <= {"youtube", "instagram"}:
        raise ValueError("platforms must contain youtube and/or instagram")
    if (not isinstance(report, dict) or report.get("pricing_model") != FIXED_REWARD_MODEL
            or not isinstance(report.get("observations"), list)
            or any(not isinstance(item, dict) for item in report["observations"])):
        raise ValueError("A fixed-reward Whop discovery report is required; CPM campaigns are separate")
    verifications = verifications or {}
    if any(not isinstance(value, BountyVerification) or key != value.bounty_id
           for key, value in verifications.items()):
        raise ValueError("Only separately reviewed bounty-bound verification models are accepted")

    results = []
    for observation in report["observations"]:
        identifier = observation.get("id")
        review = verifications.get(identifier) if isinstance(identifier, str) else None
        blockers = []
        limitations = []
        fresh = _report_fresh(report.get("observed_at"), clock)
        if not fresh:
            blockers.append("Authenticated bounty observations are undated, stale, or in the future")
        if report.get("country_filter") != country:
            blockers.append(f"Discovery was not filtered for creator residency in {country}")
        if observation.get("pricing_model", FIXED_REWARD_MODEL) != FIXED_REWARD_MODEL:
            blockers.append("This observation is not a verified fixed-reward bounty")
        if observation.get("status") != "open":
            blockers.append("The bounty is not confirmed open")
        if observation.get("business_goal_type") not in {"clipping", "ugc_content"}:
            blockers.append("Clipping or UGC requirements are not confirmed")
        country_match = observation.get("provider_reports_country_match") is True
        if not country_match:
            blockers.append(f"Provider residency rules do not confirm admission in {country}")
        if review is None or review.creator_country != country or not _fresh(review.country_eligibility, clock):
            blockers.append(f"This creator's campaign eligibility in {country} has not been verified")
        new_ok = bool(review and _fresh(review.new_accounts, clock) and review.minimum_followers == 0)
        if not new_ok:
            blockers.append("New-account acceptance and a zero-follower minimum have not both been verified")
        facts = {
            "payout_eligibility": "This creator's payout eligibility and verification have not been confirmed",
            "material_rights": "Rights to use the exact campaign materials have not been verified",
            "materials_available": "Approved campaign materials have not been verified available",
            "automation_permission": "Provider and advertiser permission for the automated workflow has not been verified",
            "requirements": "The current brief, deadline, deliverables and reward conditions have not been verified",
            "platform_permission": "Permission for a requested social platform has not been verified",
        }
        for name, message in facts.items():
            if review is None or not _fresh(getattr(review, name), clock):
                blockers.append(message)
        if review is None or (review.expires_at is None and not review.no_deadline):
            blockers.append("A campaign deadline or an explicit absence of a deadline has not been verified")
        elif review.expires_at is not None and review.expires_at <= clock:
            blockers.append("The reviewed campaign deadline has expired")
        if review is None or not requested.intersection(review.allowed_platforms):
            blockers.append("Neither requested platform is explicitly allowed by the reviewed brief")
        spots = _count(observation.get("spots_remaining"))
        if spots is None or spots <= 0:
            blockers.append("No open submission capacity has been confirmed")
        net = _number(observation.get("quoted_net_reward_amount"))
        currency = observation.get("currency")
        if net is None or net <= 0 or not isinstance(currency, str) or len(currency) != 3:
            blockers.append("A positive quoted net fixed reward and currency have not been confirmed")
        if currency != "USD":
            limitations.append("No verified USD conversion; fixed-reward size receives no monetary score")
        competition_known = bool(review and _fresh(review.competition, clock)
                                 and review.competing_entries is not None)
        if not competition_known:
            limitations.append("Competition is unknown; pending or accepted submissions are not treated as all competitors")
        limitations.extend([
            "Quoted net reward excludes unverified production costs, tax, payout costs and approval risk",
            "Open slots do not verify unreserved cash budget or guarantee acceptance and payment",
            "Fixed rewards are per approved submission and cannot be compared to CPM using an invented view count",
        ])
        verified_eligibility = bool(fresh and country_match and review and review.creator_country == country
                                    and _fresh(review.country_eligibility, clock) and new_ok
                                    and _fresh(review.payout_eligibility, clock))
        verified_requirements = bool(review and all(_fresh(getattr(review, field), clock) for field in (
            "requirements", "material_rights", "materials_available", "automation_permission", "platform_permission")))
        breakdown = {
            "quoted_net_fixed_reward": round(3 * net / (net + 25), 4) if fresh and net and currency == "USD" else 0.0,
            "verified_creator_country_and_account_eligibility": 2.0 if verified_eligibility else 0.0,
            "verified_competition": round(1.5 / (1 + review.competing_entries / 100), 4) if competition_known else 0.0,
            "observed_open_capacity": round(2 * spots / (spots + 10), 4) if fresh and spots else 0.0,
            "verified_requirements_and_permissions": 1.5 if verified_requirements else 0.0,
        }
        evidence_score = round(min(10.0, max(0.0, sum(breakdown.values()))), 2)
        results.append({
            "weaknesses": blockers + limitations,
            "blockers": blockers,
            "id": identifier,
            "title": observation.get("title"),
            "pricing_model": FIXED_REWARD_MODEL,
            "selectable": not blockers,
            "score_out_of_10": evidence_score if not blockers else None,
            "evidence_score_out_of_10": evidence_score,
            "score_status": "verified_opportunity_heuristic" if not blockers else "blocked_pending_verification",
            "breakdown": breakdown,
            "currency": currency,
            "quoted_net_reward_amount": net,
            "spots_remaining": spots,
            "observed_at": report.get("observed_at"),
            "source_api_url": observation.get("source_api_url"),
            "evidence_provenance": {
                name: {"source_url": fact.source_url, "checked_at": fact.checked_at.isoformat(),
                       "confirmed": _fresh(fact, clock)}
                for name in ["country_eligibility", "new_accounts", *facts, "competition"]
                if review is not None and (fact := getattr(review, name)) is not None
            },
            "publication_approved": False,
        })
    return sorted(results, key=lambda result: (not result["selectable"], -result["evidence_score_out_of_10"],
                                              str(result["id"])))
