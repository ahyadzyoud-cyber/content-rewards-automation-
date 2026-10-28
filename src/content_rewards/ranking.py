"""Explainable prioritization for new accounts, never a forecast of earnings."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from .models import Campaign, CampaignScore, Platform

EVIDENCE_MAX_AGE = timedelta(days=7)


def rank_campaigns(
    campaigns: list[Campaign],
    country: str = "JO",
    platforms: Iterable[Platform] = ("youtube", "instagram"),
    *,
    now: datetime | None = None,
) -> list[CampaignScore]:
    """Rank candidates for at least one requested platform.

    Use a singleton ``platforms`` list when selecting for a particular account.
    Eligibility and rights are hard selection gates, independent of the score.
    The score gives up to 3 points to reward rate, 2 to verified eligibility,
    1.5 to competition, 2 to remaining budget and 1.5 to clear requirements.
    Unknown competition receives zero points; it is not treated as no competition.
    """
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("now must include a timezone")
    requested = set(platforms)
    if not requested or not requested <= {"youtube", "instagram"}:
        raise ValueError("platforms must contain youtube and/or instagram")
    country = country.strip().upper()
    if len(country) != 2 or not country.isascii() or not country.isalpha():
        raise ValueError("country must be a two-letter country code")

    scores = []
    for campaign in campaigns:
        blockers: list[str] = []
        fresh = False
        checked = campaign.evidence_checked_at
        if checked is None:
            blockers.append("Campaign evidence has not been dated or verified")
        elif checked > clock + timedelta(minutes=5):
            blockers.append("Campaign evidence timestamp is in the future")
        elif clock - checked > EVIDENCE_MAX_AGE:
            blockers.append("Campaign evidence is older than seven days")
        else:
            fresh = True

        eligible = (
            campaign.eligibility_verified
            and bool(campaign.eligibility_evidence.strip())
            and country in campaign.eligible_countries
            and fresh
        )
        if not campaign.eligibility_verified or not campaign.eligibility_evidence.strip():
            blockers.append("Country eligibility lacks verified supporting evidence")
        if country not in campaign.eligible_countries:
            blockers.append(f"Eligibility in {country} is unknown or not permitted")
        if not requested.intersection(campaign.allowed_platforms):
            blockers.append("No requested platform is explicitly permitted")
        if campaign.allows_new_accounts is not True:
            blockers.append("New-account eligibility is unknown or not permitted")
        if campaign.minimum_followers > 0:
            blockers.append("Campaign requires an existing follower audience")
        if not campaign.requirements_verified:
            blockers.append("Campaign requirements have not been verified")
        if not campaign.rights_verified:
            blockers.append("Rights to campaign materials have not been verified")
        if not campaign.materials:
            blockers.append("No campaign-approved materials were supplied")
        if not campaign.active:
            blockers.append("Campaign is inactive")
        if campaign.remaining_budget_usd <= 0:
            blockers.append("Campaign has no remaining budget")
        if campaign.rate_per_1000_views_usd <= 0:
            blockers.append("Campaign has no positive reward rate")

        rate = campaign.rate_per_1000_views_usd
        budget = campaign.remaining_budget_usd
        competition = campaign.competition_entries
        breakdown = {
            "profitability": round(rate / (rate + 5) * 3, 4),
            "eligibility": 2.0 if eligible else 0.0,
            "competition": (
                round(1.5 / (1 + competition / 100), 4)
                if competition is not None else 0.0
            ),
            "remaining_budget": round(budget / (budget + 1000) * 2, 4),
            "requirements": (
                round(1.5 / (1 + len(campaign.requirements) / 10), 4)
                if campaign.requirements_verified and campaign.rights_verified else 0.0
            ),
        }
        scores.append(CampaignScore(
            campaign_id=campaign.id,
            score=round(min(10.0, max(0.0, sum(breakdown.values()))), 2),
            selectable=not blockers,
            blockers=blockers,
            breakdown=breakdown,
        ))
    return sorted(scores, key=lambda score: (not score.selectable, -score.score, score.campaign_id))
