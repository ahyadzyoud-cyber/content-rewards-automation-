import json

import httpx
import pytest

from content_rewards.config import Settings
from content_rewards.whop import WhopBounties, WhopError
from content_rewards.whop_broker import broker_status


@pytest.mark.parametrize("origin", ["http://worker.owner.workers.dev", "https://worker.owner.workers.dev/path",
                                   "https://worker.owner.workers.dev?token=x", "https://evil.example.com",
                                   "https://user:pass@worker.owner.workers.dev", "https://127.0.0.1",
                                   "https://worker.owner.workers.dev:8080", "https://worker.owner.workers.dev.evil.com"])
def test_invalid_broker_origin_never_sends_credentials(origin):
    with pytest.raises(WhopError):
        WhopBounties(broker_url=origin, broker_token="private-broker-token")


async def test_broker_mode_routes_only_broker_token_and_keeps_fixed_reward_model():
    def respond(request):
        assert str(request.url).startswith("https://worker.owner.workers.dev/api/bounties?")
        assert request.headers["Authorization"] == "Bearer private-broker-token"
        assert "private-whop-access-token" not in repr(request.headers)
        assert request.url.params["country"] == "JO"
        assert request.url.params["business_goal_type"] == "ugc_content"
        return httpx.Response(200, json={"data": [], "page_info": {"has_next_page": False}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await WhopBounties("private-whop-access-token", broker_url="https://worker.owner.workers.dev/",
                                   broker_token="private-broker-token", client=client).list_open_bounties(business_goal_type="ugc_content")
    assert result["pricing_model"] == "fixed_reward_per_approved_submission"
    assert result["observations"] == []
    assert result["live_publication_performed"] is False


@pytest.mark.parametrize("url,token", [("https://worker.owner.workers.dev", ""), ("", "private-token")])
def test_partial_broker_configuration_never_falls_back_to_direct_token(url, token):
    with pytest.raises(WhopError):
        WhopBounties("manual-token", broker_url=url, broker_token=token)


async def test_status_before_deployment_is_honest_and_never_calls_network():
    def unexpected(request):
        pytest.fail("An unconfigured broker must not contact a fake host")
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        result = await broker_status(Settings(whop_broker_url="", whop_broker_token=""), client=client)
    assert result["status"] == "awaiting_owner_cloud_authorization"
    assert result["requested_scope"] == "bounty:basic"
    assert not result["durable_renewal_verified"] and not result["live_publishing"]


async def test_status_drops_arbitrary_private_fields_and_nonboolean_proof():
    def respond(request):
        assert request.url.path == "/api/status"
        assert request.headers["Authorization"] == "Bearer broker-private"
        assert "broker-private" not in str(request.url)
        return httpx.Response(200, json={"authorized": True, "scope_verified": "true", "live_publishing": False,
                                         "account_id": "private-id", "access_token": "upstream-private"})
    config = Settings(whop_broker_url="https://worker.owner.workers.dev", whop_broker_token="broker-private")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await broker_status(config, client=client)
    assert result["authorized"] is True
    assert "scope_verified" not in result
    assert "private" not in json.dumps(result)
    assert "broker-private" not in repr(config)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
async def test_status_errors_and_redirects_are_not_followed_or_echoed(status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://evil.example.com"}, text="private-upstream")
    config = Settings(whop_broker_url="https://worker.owner.workers.dev", whop_broker_token="broker-private")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(WhopError) as caught:
            await broker_status(config, client=client)
    assert "private" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{"live_publishing": True}, {"live_publishing": "false"}, [], "invalid"])
async def test_status_does_not_report_safe_for_invalid_response(payload):
    config = Settings(whop_broker_url="https://worker.owner.workers.dev", whop_broker_token="broker-private")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        with pytest.raises(WhopError):
            await broker_status(config, client=client)
