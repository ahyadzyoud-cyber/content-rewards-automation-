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
