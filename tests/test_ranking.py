from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from content_rewards.models import Campaign
from content_rewards.ranking import rank_campaigns

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def candidate(**updates):
    data = {
        "id": "approved", "title": "Verified demo", "source": "manual",
        "source_url": "https://example.com/campaign", "rate_per_1000_views_usd": 10,
        "remaining_budget_usd": 2000, "competition_entries": 20,
        "eligible_countries": ["JO"], "eligibility_verified": True,
        "eligibility_evidence": "Campaign terms explicitly permit Jordan",
        "allowed_platforms": ["youtube", "instagram"], "allows_new_accounts": True,
        "requirements_verified": True, "rights_verified": True,
        "materials": ["approved.mp4"], "evidence_checked_at": NOW,
    }
    return Campaign(**(data | updates))


def test_verified_campaign_selected_for_jordan_and_scores_are_explained():
    score = rank_campaigns([candidate()], now=NOW)[0]
    assert score.selectable
    assert not score.blockers
    assert score.score == round(sum(score.breakdown.values()), 2)
    assert 0 <= score.score <= 10


@pytest.mark.parametrize("updates,reason", [
    ({"eligible_countries": []}, "Eligibility in JO"),
    ({"eligible_countries": ["US"]}, "Eligibility in JO"),
    ({"eligibility_verified": False}, "supporting evidence"),
    ({"eligibility_evidence": ""}, "supporting evidence"),
    ({"allows_new_accounts": None}, "New-account eligibility"),
    ({"allows_new_accounts": False}, "New-account eligibility"),
    ({"minimum_followers": 1}, "follower audience"),
    ({"allowed_platforms": []}, "platform"),
    ({"requirements_verified": False}, "requirements"),
    ({"rights_verified": False}, "Rights"),
    ({"materials": []}, "materials"),
    ({"remaining_budget_usd": 0}, "remaining budget"),
    ({"rate_per_1000_views_usd": 0}, "reward rate"),
    ({"active": False}, "inactive"),
    ({"evidence_checked_at": None}, "dated"),
    ({"evidence_checked_at": NOW - timedelta(days=8)}, "older than"),
    ({"evidence_checked_at": NOW + timedelta(hours=1)}, "future"),
])
def test_unknown_and_disallowed_conditions_block_selection(updates, reason):
    score = rank_campaigns([candidate(**updates)], now=NOW)[0]
    assert not score.selectable
    assert any(reason in blocker for blocker in score.blockers)


def test_platform_selection_requires_explicit_support():
    only_youtube = candidate(allowed_platforms=["youtube"])
    assert rank_campaigns([only_youtube], platforms=["youtube"], now=NOW)[0].selectable
    assert not rank_campaigns([only_youtube], platforms=["instagram"], now=NOW)[0].selectable


def test_unknown_competition_is_not_treated_as_zero_competitors():
    unknown = candidate(id="unknown", competition_entries=None)
    zero = candidate(id="zero", competition_entries=0)
    scores = rank_campaigns([unknown, zero], now=NOW)
    assert [s.campaign_id for s in scores] == ["zero", "unknown"]
    assert scores[1].breakdown["competition"] == 0


def test_higher_rate_and_budget_increase_priority_and_selection_precedes_score():
    low = candidate(id="low", rate_per_1000_views_usd=1, remaining_budget_usd=100)
    high = candidate(id="high", rate_per_1000_views_usd=100, remaining_budget_usd=10000)
    blocked = candidate(id="blocked", rate_per_1000_views_usd=1e100,
                        remaining_budget_usd=1e100, allows_new_accounts=None)
    scores = rank_campaigns([low, blocked, high], now=NOW)
    assert [s.campaign_id for s in scores] == ["high", "low", "blocked"]
    assert all(0 <= s.score <= 10 for s in scores)


def test_largest_finite_money_does_not_overflow_score_components():
    score = rank_campaigns([candidate(rate_per_1000_views_usd=1.79e308,
                                     remaining_budget_usd=1.79e308)], now=NOW)[0]
    assert score.score <= 10
    assert score.breakdown["profitability"] == 3
    assert score.breakdown["remaining_budget"] == 2


@pytest.mark.parametrize("updates", [
    {"rate_per_1000_views_usd": float("nan")},
    {"rate_per_1000_views_usd": float("inf")},
    {"remaining_budget_usd": -1},
    {"competition_entries": -1},
    {"competition_entries": True},
    {"source_url": "http://example.com"},
    {"source_url": "https://user:secret@example.com"},
    {"evidence_checked_at": NOW.replace(tzinfo=None)},
    {"eligible_countries": ["Jordan"]},
    {"id": "../escape"},
])
def test_invalid_campaign_records_are_rejected(updates):
    with pytest.raises(ValidationError):
        candidate(**updates)


def test_countries_are_normalized_and_unknown_remains_unknown():
    assert candidate(eligible_countries=["jo", "JO"]).eligible_countries == ["JO"]
    campaign = Campaign(id="unknown", title="Unknown", source="whop",
                        source_url="https://example.com/campaign",
                        rate_per_1000_views_usd=10, remaining_budget_usd=1000)
    assert not rank_campaigns([campaign], now=NOW)[0].selectable


def test_invalid_query_inputs_rejected():
    with pytest.raises(ValueError):
        rank_campaigns([], platforms=[])
    with pytest.raises(ValueError):
        rank_campaigns([], country="Jordan")
    with pytest.raises(ValueError):
        rank_campaigns([], now=NOW.replace(tzinfo=None))
