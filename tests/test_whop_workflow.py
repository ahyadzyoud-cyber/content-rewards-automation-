import pytest

from content_rewards.config import Settings
from content_rewards.service import Blocked, Workflow
from content_rewards.whop import WhopBounties


async def test_missing_whop_authorization_blocks_before_network(tmp_path, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Missing credentials must not initiate Whop discovery")
    monkeypatch.setattr(WhopBounties, "list_open_bounties", unexpected)
    flow = Workflow(Settings(database=tmp_path / "db.sqlite", whop_token=""))
    with pytest.raises(Blocked, match="bounty:basic:read"):
        await flow.discover_whop()
    assert not flow.store.list("whop_discovery")


async def test_whop_discovery_keeps_fixed_rewards_separate_and_private(tmp_path, monkeypatch):
    async def listed(self, country, business_goal_type, max_pages):
        assert country == "JO" and business_goal_type == "clipping" and max_pages == 2
        return {"pricing_model": "fixed_reward_per_approved_submission", "observed_at": "2026-10-28T00:00:00Z",
                "country_filter": "JO", "pagination_complete": True, "observations": [{
                    "id": "bnty_fixture", "title": "Synthetic bounty", "currency": "USD",
                    "gross_reward_amount": 10, "spots_remaining": 1, "provider_reports_country_match": True,
                    "new_account_eligibility_verified": False, "raw": {"private_brief": "not-for-public-checkpoints"},
                }]}
    monkeypatch.setattr(WhopBounties, "list_open_bounties", listed)
    config = Settings(database=tmp_path / "db.sqlite", whop_token="private-whop-test-token")
    flow = Workflow(config)
    result = await flow.discover_whop(max_pages=2)
    assert result["pricing_model"] == "fixed_reward_per_approved_submission"
    assert result["opportunities"][0]["gross_reward_amount"] == 10
    assert "raw" not in result["opportunities"][0]
    assert result["eligible_campaigns_verified"] is False
    assert result["live_publication_performed"] is False
    assert not flow.store.list("campaign") and not flow.store.list("job")
    assert flow.store.get("whop_discovery", "JO:clipping")["observations"][0]["raw"]
    assert "private-whop-test-token" not in repr(config)
