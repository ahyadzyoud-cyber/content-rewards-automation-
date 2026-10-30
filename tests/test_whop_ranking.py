from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from content_rewards.whop_ranking import (
    BountyEvidence,
    BountyVerification,
    rank_whop_bounties,
)

NOW = datetime(2026, 10, 29, tzinfo=UTC)


def observation(identifier="bnty_fixture", **updates):
    return {"id": identifier, "title": "Synthetic fixed-reward fixture", "status": "open",
            "pricing_model": "fixed_reward_per_approved_submission", "business_goal_type": "clipping",
            "currency": "USD", "quoted_net_reward_amount": 25, "spots_remaining": 10,
            "accepted_submissions_limit": 10, "accepted_submissions_per_user_limit": 1,
            "viewer_accepted_submissions_count": 0,
            "provider_reports_country_match": True,
            "source_api_url": "https://api.whop.com/api/v1/bounties/" + identifier} | updates


def report(*records, **updates):
    return {"pricing_model": "fixed_reward_per_approved_submission", "country_filter": "JO",
            "observed_at": NOW.isoformat(), "observations": list(records or [observation()])} | updates


def fact(**updates):
    return BountyEvidence.model_validate({"confirmed": True, "checked_at": NOW,
        "source_url": "https://whop.com/campaign-reviewed-terms",
        "detail": "Synthetic operator-reviewed evidence; this is not a real opportunity."} | updates)


def verification(**updates):
    fields = {"bounty_id": "bnty_fixture", "creator_country": "JO", "minimum_followers": 0,
              "allowed_platforms": ["youtube"], "competing_entries": 0,
              "expires_at": NOW + timedelta(days=1)}
    for name in ("country_eligibility", "new_accounts", "payout_eligibility", "material_rights",
                 "materials_available", "automation_permission", "requirements", "platform_permission", "competition"):
        fields[name] = fact()
    return BountyVerification.model_validate(fields | updates)


def test_discovery_alone_does_not_verify_admission_or_generate_cpm():
    result = rank_whop_bounties(report(), now=NOW)[0]
    assert next(iter(result)) == "weaknesses"
    assert result["selectable"] is False and result["score_out_of_10"] is None
    assert result["score_status"] == "blocked_pending_verification"
    assert result["evidence_score_out_of_10"] > 0
    assert result["weaknesses"][0].startswith("This creator's campaign eligibility")
    assert any("payout" in reason for reason in result["blockers"])
    assert any("Rights" in reason for reason in result["blockers"])
    assert any("automation" in reason.lower() or "automated" in reason for reason in result["blockers"])
    assert result["publication_approved"] is False
    assert "rate_per_1000_views_usd" not in result


def test_verified_fixed_reward_is_scored_with_provenance_without_publication_approval():
    reviewed = verification()
    result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["selectable"] and result["blockers"] == []
    assert result["score_out_of_10"] == 7.5
    assert result["pricing_model"] == "fixed_reward_per_approved_submission"
    assert result["evidence_provenance"]["payout_eligibility"]["confirmed"] is True
    assert result["evidence_provenance"]["payout_eligibility"]["source_url"].startswith("https://whop.com/")
    assert result["publication_approved"] is False
    assert any("production costs" in weakness for weakness in result["weaknesses"])
    assert any("unreserved cash budget" in weakness for weakness in result["weaknesses"])


@pytest.mark.parametrize("field", ["country_eligibility", "new_accounts", "payout_eligibility", "material_rights",
                                   "materials_available", "automation_permission", "requirements", "platform_permission"])
def test_every_required_fact_is_separately_gated(field):
    for value in (None, fact(confirmed=False), fact(checked_at=NOW - timedelta(days=8)),
                  fact(checked_at=NOW + timedelta(hours=1))):
        reviewed = verification(**{field: value})
        result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert not result["selectable"] and result["score_out_of_10"] is None


@pytest.mark.parametrize("updates", [
    {"minimum_followers": 1}, {"minimum_followers": None}, {"allowed_platforms": ["instagram"]},
    {"creator_country": "US"},
])
def test_new_account_creator_and_platform_restrictions_prevent_selection(updates):
    reviewed = verification(**updates)
    result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, platforms=["youtube"], now=NOW)[0]
    assert not result["selectable"]


@pytest.mark.parametrize("updates", [{"spots_remaining": 0}, {"spots_remaining": True},
    {"quoted_net_reward_amount": 0}, {"quoted_net_reward_amount": float("nan")},
    {"provider_reports_country_match": False}, {"status": "closed"},
    {"business_goal_type": "unknown"}, {"pricing_model": "cpm"}])
def test_live_observation_gates_cannot_be_overridden_by_evidence(updates):
    reviewed = verification()
    result = rank_whop_bounties(report(observation(**updates)), {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert not result["selectable"]


@pytest.mark.parametrize("goal", [None, "other", "post_engagement"])
def test_all_goal_research_retains_uncategorized_offers_without_expanding_video_eligibility(goal):
    reviewed = verification()
    result = rank_whop_bounties(report(observation(business_goal_type=goal), business_goal_type="all",
                                      discovery_strategy="all_open_goals"),
                               {reviewed.bounty_id: reviewed}, now=NOW)
    assert len(result) == 1 and result[0]["id"] == reviewed.bounty_id
    assert result[0]["selectable"] is False and result[0]["score_out_of_10"] is None
    assert "Clipping or UGC requirements are not confirmed" in result[0]["blockers"]
    assert result[0]["publication_approved"] is False


def test_stale_discovery_or_mismatched_country_cannot_be_cleared_by_fresh_review():
    reviewed = verification()
    for updates in ({"observed_at": (NOW - timedelta(days=8)).isoformat()},
                    {"observed_at": "bad"}, {"observed_at": NOW.replace(tzinfo=None).isoformat()},
                    {"country_filter": "US"}):
        result = rank_whop_bounties(report(**updates), {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert not result["selectable"]


def test_competition_is_unknown_without_its_own_fresh_evidence():
    for updates in ({"competition": None}, {"competition": fact(confirmed=False)}, {"competing_entries": None}):
        reviewed = verification(**updates)
        item = observation(unresolved_submissions_count=0, accepted_submissions_count=0)
        result = rank_whop_bounties(report(item), {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert result["selectable"]
        assert result["breakdown"]["verified_competition"] == 0
        assert any("Competition is unknown" in weakness for weakness in result["weaknesses"])


def test_expired_or_unknown_deadline_blocks_and_explicit_no_deadline_is_supported():
    for updates in ({"expires_at": NOW}, {"expires_at": None}):
        reviewed = verification(**updates)
        result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert not result["selectable"]
        assert any("deadline" in blocker for blocker in result["blockers"])
    reviewed = verification(expires_at=None, no_deadline=True)
    assert rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]["selectable"]


def test_other_currency_does_not_get_invented_exchange_or_usd_reward_points():
    reviewed = verification()
    result = rank_whop_bounties(report(observation(currency="JPY", quoted_net_reward_amount=100000)),
                               {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["breakdown"]["quoted_net_fixed_reward"] == 0
    assert any("USD conversion" in weakness for weakness in result["weaknesses"])


def test_verified_opportunities_sort_before_lucrative_unverified_ones_and_do_not_mutate_inputs():
    reviewed = verification()
    payload = report(observation("bnty_unverified", quoted_net_reward_amount=10000), observation())
    result = rank_whop_bounties(payload, {reviewed.bounty_id: reviewed}, now=NOW)
    assert [item["id"] for item in result] == ["bnty_fixture", "bnty_unverified"]
    assert "score_out_of_10" not in payload["observations"][0]


def test_cpm_and_untyped_imported_verifications_are_rejected():
    with pytest.raises(ValueError, match="CPM"):
        rank_whop_bounties(report(pricing_model="cpm"), now=NOW)
    with pytest.raises(ValueError, match="separately reviewed"):
        rank_whop_bounties(report(), {"bnty_fixture": {"new_accounts": True}}, now=NOW)
    with pytest.raises(ValueError, match="bounty-bound"):
        rank_whop_bounties(report(), {"bnty_other": verification()}, now=NOW)


@pytest.mark.parametrize("updates", [{"confirmed": "true"}, {"checked_at": NOW.replace(tzinfo=None)},
    {"source_url": "https://whop.com/evidence?token=secret"}, {"source_url": "http://whop.com/evidence"},
    {"source_url": "https://owner:secret@whop.com/evidence"}, {"detail": "   "}])
def test_evidence_rejects_ambiguous_flags_dates_and_secret_bearing_urls(updates):
    with pytest.raises(ValidationError):
        fact(**updates)


def economic_verification(**updates):
    return verification(**({
        "production_cost_usd": 2.0,
        "production_hours": 0.5,
        "acceptance_probability": 0.8,
        "production_cost_evidence": fact(),
        "production_time_evidence": fact(),
        "acceptance_probability_evidence": fact(),
    } | updates))


def test_fresh_separately_reviewed_economics_create_only_a_planning_scenario():
    reviewed = economic_verification()
    result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]
    scenario = result["economic_scenario"]
    assert scenario["status"] == "reviewed_assumption_scenario"
    assert scenario["expected_net_usd"] == 18.0  # .8 * 25 - 2, costs apply to every attempt.
    assert scenario["expected_net_per_hour_usd"] == 36.0
    assert scenario["assumptions"] == {
        "production_cost_usd": 2.0, "production_hours": 0.5, "acceptance_probability": 0.8,
    }
    assert result["economic_priority_rank"] == 1
    assert result["score_out_of_10"] == 7.5  # Economic assumptions do not change verified evidence.
    assert result["publication_approved"] is False
    assert any("no acceptance, earnings or payout" in reason for reason in scenario["limitations"])
    for name in ("production_cost_evidence", "production_time_evidence", "acceptance_probability_evidence"):
        assert result["evidence_provenance"][name]["confirmed"] is True


@pytest.mark.parametrize("field", [
    "production_cost_evidence", "production_time_evidence", "acceptance_probability_evidence",
])
def test_each_economic_assumption_requires_its_own_fresh_review_without_changing_eligibility(field):
    for value in (None, fact(confirmed=False), fact(checked_at=NOW - timedelta(days=8)),
                  fact(checked_at=NOW + timedelta(hours=1))):
        reviewed = economic_verification(**{field: value})
        result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert result["selectable"] and result["blockers"] == []
        assert result["economic_scenario"]["status"] == "unavailable"
        assert result["economic_scenario"]["expected_net_usd"] is None
        assert result["economic_scenario"]["expected_net_per_hour_usd"] is None
        assert result["economic_priority_rank"] is None


@pytest.mark.parametrize("field", ["production_cost_usd", "production_hours", "acceptance_probability"])
def test_missing_economic_values_are_not_assumed_zero_or_inferred_from_api_counts(field):
    reviewed = economic_verification(**{field: None})
    payload = report(observation(accepted_submissions_count=100, unresolved_submissions_count=0))
    result = rank_whop_bounties(payload, {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["selectable"]
    assert result["economic_scenario"]["status"] == "unavailable"
    assert result["economic_scenario"]["assumptions"] is None
    assert result["economic_priority_rank"] is None


@pytest.mark.parametrize("updates", [
    {"production_cost_usd": -1}, {"production_cost_usd": True},
    {"production_cost_usd": float("nan")}, {"production_cost_usd": float("inf")},
    {"production_hours": 0}, {"production_hours": -1}, {"production_hours": True},
    {"production_hours": float("inf")}, {"acceptance_probability": -0.1},
    {"acceptance_probability": 1.1}, {"acceptance_probability": True},
    {"acceptance_probability": float("nan")},
])
def test_economic_assumptions_reject_invalid_or_ambiguous_numbers(updates):
    with pytest.raises(ValidationError):
        economic_verification(**updates)


def test_economic_planning_does_not_invent_currency_conversion_or_use_stale_quote():
    reviewed = economic_verification()
    for payload in (report(observation(currency="EUR")),
                    report(observed_at=(NOW - timedelta(days=8)).isoformat())):
        result = rank_whop_bounties(payload, {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert result["economic_scenario"]["status"] == "unavailable"
        assert result["economic_scenario"]["expected_net_usd"] is None


def test_economic_priority_compares_only_complete_eligible_scenarios_and_keeps_unknown_queue_position():
    reviews = {
        "bnty_unknown": verification(bounty_id="bnty_unknown"),
        "bnty_slow": economic_verification(bounty_id="bnty_slow", production_hours=10.0),
        "bnty_fast": economic_verification(bounty_id="bnty_fast"),
        "bnty_blocked": economic_verification(bounty_id="bnty_blocked", new_accounts=None),
    }
    payload = report(observation("bnty_unknown", quoted_net_reward_amount=100),
                     observation("bnty_slow", quoted_net_reward_amount=50),
                     observation("bnty_fast", quoted_net_reward_amount=25),
                     observation("bnty_blocked", quoted_net_reward_amount=1000))
    results = rank_whop_bounties(payload, reviews, now=NOW)
    assert [result["id"] for result in results] == ["bnty_unknown", "bnty_slow", "bnty_fast", "bnty_blocked"]
    by_id = {result["id"]: result for result in results}
    assert by_id["bnty_unknown"]["economic_priority_rank"] is None
    assert by_id["bnty_fast"]["economic_priority_rank"] == 1
    assert by_id["bnty_slow"]["economic_priority_rank"] == 2
    assert by_id["bnty_blocked"]["economic_priority_rank"] is None


def test_small_rewards_and_negative_scenarios_remain_in_the_queue_without_a_cutoff():
    reviewed = economic_verification(acceptance_probability=0.0)
    result = rank_whop_bounties(report(observation(quoted_net_reward_amount=0.01)),
                               {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["selectable"] and result["blockers"] == []
    assert result["quoted_net_reward_amount"] == 0.01
    assert result["economic_scenario"]["expected_net_usd"] == -2.0
    assert result["economic_scenario"]["expected_net_per_hour_usd"] == -4.0
    assert result["economic_priority_rank"] == 1


def test_extreme_finite_inputs_do_not_emit_infinite_economic_estimates():
    reviewed = economic_verification(production_hours=5e-324)
    result = rank_whop_bounties(report(), {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["selectable"]
    assert result["economic_scenario"]["status"] == "unavailable"
    assert result["economic_scenario"]["expected_net_per_hour_usd"] is None
    assert any("finite numeric limits" in reason for reason in result["weaknesses"])


@pytest.mark.parametrize("updates,reason", [
    ({"accepted_submissions_per_user_limit": None}, "per-user winner limit"),
    ({"accepted_submissions_per_user_limit": 0}, "per-user winner limit"),
    ({"accepted_submissions_per_user_limit": True}, "per-user winner limit"),
    ({"accepted_submissions_per_user_limit": -1}, "per-user winner limit"),
    ({"accepted_submissions_per_user_limit": 11}, "exceeds"),
    ({"accepted_submissions_limit": None}, "total winner limit"),
    ({"accepted_submissions_limit": 0}, "total winner limit"),
    ({"viewer_accepted_submissions_count": None}, "accepted-submission count"),
    ({"viewer_accepted_submissions_count": True}, "accepted-submission count"),
    ({"viewer_accepted_submissions_count": -1}, "accepted-submission count"),
    ({"viewer_accepted_submissions_count": 1}, "exhausted"),
    ({"viewer_accepted_submissions_count": 2}, "exhausted"),
])
def test_owner_winner_allowance_blocks_even_with_global_slots_and_reviewed_eligibility(updates, reason):
    reviewed = verification()
    result = rank_whop_bounties(report(observation(**updates)), {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["spots_remaining"] == 10
    assert not result["selectable"] and result["score_out_of_10"] is None
    assert any(reason in blocker for blocker in result["blockers"])


def test_old_stored_observations_cannot_assume_a_default_or_an_unused_owner_allowance():
    reviewed = verification()
    for field in ("accepted_submissions_limit", "accepted_submissions_per_user_limit", "viewer_accepted_submissions_count"):
        old_record = observation()
        del old_record[field]
        result = rank_whop_bounties(report(old_record), {reviewed.bounty_id: reviewed}, now=NOW)[0]
        assert not result["selectable"]
        assert result[field] is None


def test_personal_winner_cap_is_distinct_from_global_pending_submissions():
    reviewed = verification()
    result = rank_whop_bounties(report(observation(accepted_submissions_per_user_limit=2,
        viewer_accepted_submissions_count=1, unresolved_submissions_count=9)),
        {reviewed.bounty_id: reviewed}, now=NOW)[0]
    assert result["selectable"]
    assert result["accepted_submissions_per_user_limit"] == 2
    assert result["viewer_accepted_submissions_count"] == 1
    assert any("do not verify this creator's pending proofs" in reason for reason in result["weaknesses"])
