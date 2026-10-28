from datetime import UTC, datetime

import pytest

from content_rewards.config import Settings
from content_rewards.models import Campaign
from content_rewards.ranking import rank_campaigns
from content_rewards.service import Workflow


def record(**updates):
    return {"id": "permission-fixture", "title": "Synthetic permission fixture", "source": "manual",
            "source_url": "https://example.com/fixture", "rate_per_1000_views_usd": 2,
            "remaining_budget_usd": 100, "eligible_countries": ["JO"], "eligibility_verified": True,
            "eligibility_evidence": "Synthetic fixture only", "allowed_platforms": ["youtube"],
            "allows_new_accounts": True, "requirements_verified": True, "rights_verified": True,
            "materials": ["approved-fixture.mp4"], "evidence_checked_at": datetime.now(UTC).isoformat()} | updates


@pytest.mark.parametrize("source", ["whop", "content_rewards", "vyro"])
@pytest.mark.parametrize("updates", [{}, {"automation_authorized": True}, {"automation_evidence": "Terms excerpt"}])
def test_provider_automation_needs_both_authorization_and_evidence(source, updates):
    score = rank_campaigns([Campaign.model_validate(record(source=source, **updates))])[0]
    assert not score.selectable
    assert any("Provider authorization" in blocker for blocker in score.blockers)


@pytest.mark.parametrize("source", ["whop", "content_rewards", "vyro"])
def test_verified_provider_authorization_can_pass_other_selection_gates(source):
    campaign = Campaign.model_validate(record(source=source, automation_authorized=True,
                                               automation_evidence="Owner attests provider-approved test workflow"))
    assert rank_campaigns([campaign])[0].selectable


def test_owner_manual_campaign_still_supports_local_draft_work():
    assert rank_campaigns([Campaign.model_validate(record())])[0].selectable


def test_untrusted_feed_cannot_grant_provider_automation_permission(tmp_path):
    flow = Workflow(Settings(database=tmp_path / "db.sqlite"))
    flow.import_campaigns([record(source="vyro", automation_authorized=True,
                                 automation_evidence="Feed self-assertion")], untrusted_feed=True)
    assert flow.store.get("campaign", "permission-fixture")["automation_authorized"] is False
    assert not flow.rank()[0]["selectable"]
