import json

import httpx
import pytest

from content_rewards.whop import WhopBounties, WhopError


def bounty(identifier="bnty_actual", **updates):
    return {"id": identifier, "title": "Test fixture clipping bounty", "description": "Actual terms must be reviewed",
            "status": "open", "business_goal_type": "clipping", "currency": "usd",
            "gross_reward_amount": 15, "net_reward_amount": 10.5, "budget_amount": 150,
            "gross_paid_out_amount": 30, "accepted_submissions_count": 2,
            "accepted_submissions_limit": 10, "unresolved_submissions_count": 1,
            "spots_remaining": 7, "allowed_country_codes": ["JO"],
            "accepted_deliverable_types": ["content_url"], "requirements": "do not invent terms"} | updates


def page(records, *, after=None, more=False):
    return {"data": records, "page_info": {"end_cursor": after, "start_cursor": None,
                                           "has_next_page": more, "has_previous_page": False}}


async def test_documented_filters_headers_pagination_and_distinct_reward_model():
    requests = []
    def respond(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.whop.com" and request.url.path == "/api/v1/bounties"
        assert request.headers["authorization"] == "Bearer private-owner-token"
        assert request.headers["api-version-date"] == "2026-10-28"
        assert request.url.params["status"] == "open"
        assert request.url.params["business_goal_type"] == "clipping"
        assert request.url.params["country"] == "JO"
        assert "private-owner-token" not in str(request.url)
        if len(requests) == 1:
            assert "after" not in request.url.params
            return httpx.Response(200, json=page([bounty()], after="cursor-next", more=True))
        assert request.url.params["after"] == "cursor-next"
        return httpx.Response(200, json=page([bounty("bnty_next", allowed_country_codes=[])]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await WhopBounties("private-owner-token", client=client).list_open_bounties()
    assert len(requests) == 2 and result["pagination_complete"] is True
    assert result["pages_fetched"] == 2 and len(result["observations"]) == 2
    observation = result["observations"][0]
    assert observation["pricing_model"] == "fixed_reward_per_approved_submission"
    assert observation["gross_reward_amount"] == 15 and observation["quoted_net_reward_amount"] == 10.5
    assert observation["raw"]["requirements"] == "do not invent terms"
    assert observation["provider_reports_country_match"] is True
    assert result["observations"][1]["provider_reports_country_match"] is True
    assert "rate_per_1000_views_usd" not in json.dumps(result)
    for field in ("new_account_eligibility_verified", "rights_verified", "payout_verified", "publication_approved"):
        assert observation[field] is False
    assert result["eligible_campaigns_verified"] is False


async def test_request_bounds_report_partial_pagination_without_claiming_completeness():
    def respond(request):
        return httpx.Response(200, json=page([bounty()], after="next", more=True))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await WhopBounties("test-token", client=client).list_open_bounties(max_pages=1)
    assert result["pagination_complete"] is False and result["pages_fetched"] == 1


async def test_api_country_mismatch_does_not_verify_jordan_eligibility():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=page([bounty(allowed_country_codes=["US"])])))) as client:
        result = await WhopBounties("test-token", client=client).list_open_bounties()
    assert result["observations"][0]["provider_reports_country_match"] is False
    assert result["eligible_campaigns_verified"] is False


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 500])
async def test_provider_errors_never_echo_body_or_retry(status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://other.example.com/private"},
                              json={"error": "private-owner-token", "echo": "sensitive upstream body"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(WhopError) as caught:
            await WhopBounties("private-owner-token", client=client).list_open_bounties()
    assert len(calls) == 1
    assert "private-owner-token" not in str(caught.value) and "sensitive" not in str(caught.value)


async def test_network_errors_are_sanitized():
    def respond(request):
        raise httpx.ReadTimeout("private-owner-token", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(WhopError) as caught:
            await WhopBounties("private-owner-token", client=client).list_open_bounties()
    assert "private-owner-token" not in str(caught.value)


@pytest.mark.parametrize("changes", [
    {"data": "not records"}, {"page_info": {}}, {"page_info": {"has_next_page": "false"}},
    {"page_info": {"has_next_page": True, "end_cursor": None}},
    {"data": [bounty(gross_reward_amount=-1)]}, {"data": [bounty(net_reward_amount=True)]},
    {"data": [bounty(gross_reward_amount=float("inf"))]}, {"data": [bounty(spots_remaining=-1)]},
    {"data": [bounty(allowed_country_codes=["Jordan"])]}, {"data": [bounty(id="https://bad.example/")]},
])
async def test_malformed_provider_records_or_pagination_fail_closed(changes):
    payload = page([bounty()]) | changes
    # Non-finite numbers are deliberately passed as raw malformed-provider JSON.
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=json.dumps(payload)))) as client:
        with pytest.raises(WhopError):
            await WhopBounties("test-token", client=client).list_open_bounties()


async def test_repeated_cursor_and_duplicate_records_are_rejected():
    for records in ([bounty()], []):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=page(records, after="repeat", more=True)))) as client:
            with pytest.raises(WhopError):
                await WhopBounties("test-token", client=client).list_open_bounties()


@pytest.mark.parametrize("params", [{"country": "Jordan"}, {"business_goal_type": "paid_ads"},
                                    {"first": 101}, {"first": True}, {"max_pages": 0}, {"max_pages": 21}])
async def test_invalid_queries_make_no_request(params):
    def respond(request):
        pytest.fail("Invalid input must not reach Whop")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(WhopError):
            await WhopBounties("test-token", client=client).list_open_bounties(**params)


@pytest.mark.parametrize("token", ["", " ", "bad\ntoken", "bad\rtoken"])
def test_missing_or_invalid_owner_authorization_is_rejected(token):
    with pytest.raises(WhopError):
        WhopBounties(token)


async def test_ugc_uses_its_own_documented_goal_filter():
    def respond(request):
        assert request.url.params["business_goal_type"] == "ugc_content"
        return httpx.Response(200, json=page([bounty(business_goal_type="ugc_content")]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await WhopBounties("test-token", client=client).list_open_bounties(business_goal_type="ugc_content")
    assert result["business_goal_type"] == "ugc_content"
