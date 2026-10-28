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


def test_known_expired_deadline_blocks_but_unknown_deadline_remains_draft_eligible():
    unknown = candidate(expires_at=None)
    future = candidate(id="future", expires_at=NOW + timedelta(seconds=1))
    expired = candidate(id="expired", expires_at=NOW - timedelta(seconds=1))
    boundary = candidate(id="boundary", expires_at=NOW)
    by_id = {score.campaign_id: score for score in rank_campaigns([unknown, future, expired, boundary], now=NOW)}
    assert by_id["approved"].selectable
    assert by_id["future"].selectable
    for campaign_id in ("expired", "boundary"):
        assert not by_id[campaign_id].selectable
        assert "Campaign deadline has expired" in by_id[campaign_id].blockers


def test_creator_residency_is_distinct_from_audience_geography_and_payout_evidence():
    campaign = candidate(eligible_countries=["jo"], audience_country_requirements=["us", "US"],
                         qualifying_views_terms="US organic views only; first 30 days",
                         maximum_reward_per_video_usd=100, payout_eligibility_verified=True,
                         payout_evidence="Provider account evidence supports Jordan payout")
    assert campaign.eligible_countries == ["JO"]
    assert campaign.audience_country_requirements == ["US"]
    assert campaign.maximum_reward_per_video_usd == 100
    assert campaign.payout_eligibility_verified
    assert rank_campaigns([campaign], country="JO", now=NOW)[0].selectable
    assert not rank_campaigns([campaign], country="US", now=NOW)[0].selectable


@pytest.mark.parametrize("updates", [
    {"expires_at": NOW.replace(tzinfo=None)},
    {"maximum_reward_per_video_usd": -1},
    {"maximum_reward_per_video_usd": float("nan")},
    {"maximum_reward_per_video_usd": float("inf")},
    {"audience_country_requirements": ["United States"]},
])
def test_new_business_terms_reject_invalid_dates_countries_and_reward_caps(updates):
    with pytest.raises(ValidationError):
        candidate(**updates)


def test_new_terms_remain_unknown_for_existing_records_instead_of_being_invented():
    campaign = candidate()
    assert campaign.expires_at is None
    assert campaign.maximum_reward_per_video_usd is None
    assert campaign.qualifying_views_terms == ""
    assert campaign.audience_country_requirements == []
    assert not campaign.payout_eligibility_verified
    assert campaign.payout_evidence == ""
