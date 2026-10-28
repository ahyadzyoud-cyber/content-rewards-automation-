import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial

import httpx

from content_rewards import oauth
from content_rewards.config import Settings
from content_rewards.integrations import YouTubePublisher
from content_rewards.readiness import verify_accounts
from content_rewards.service import Workflow


async def test_refresh_connect_publish_and_track_share_renewable_credentials(tmp_path, monkeypatch):
    requests = []
    def provider(request):
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "renewed-access", "token_type": "Bearer", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer renewed-access"
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json={"items": [{"id": "actual-target"}]})
        if request.method == "POST":
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=resume"})
        if request.method == "PUT":
            return httpx.Response(200, json={"id": "published-id"})
        return httpx.Response(200, json={"items": [{"statistics": {"viewCount": "42"}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        monkeypatch.setattr(oauth, "YouTubeTokenProvider", partial(oauth.YouTubeTokenProvider, client=client))
        @asynccontextmanager
        async def api_client(self):
            yield client
        monkeypatch.setattr(YouTubePublisher, "_client", api_client)
        config = Settings(database=tmp_path / "state.sqlite", media_root=tmp_path / "media",
                          youtube_channel_id="actual-target", google_client_id="public-client",
                          google_client_secret="private-client", youtube_refresh_token="private-refresh",
                          youtube_token="old-unknown-expiry", live_publishing=True)
        flow = Workflow(config)
        source = tmp_path / "source.mp4"
        source.write_bytes(b"approved material")
        flow.import_campaigns([{
            "id": "fixture", "title": "Synthetic wiring fixture", "source": "manual",
            "source_url": "https://example.com/fixture", "rate_per_1000_views_usd": 2,
            "remaining_budget_usd": 100, "eligible_countries": ["JO"], "eligibility_verified": True,
            "eligibility_evidence": "Synthetic fixture only", "allowed_platforms": ["youtube"],
            "allows_new_accounts": True, "requirements_verified": True, "rights_verified": True,
            "materials": [str(source)], "evidence_checked_at": datetime.now(UTC).isoformat(),
        }])
        def render(source, output, **kwargs):
            output.write_bytes(b"reviewed mp4")
        monkeypatch.setattr("content_rewards.service.render_short", render)
        job = flow.plan("fixture", "youtube", source, "Reviewed test video")
        flow.render(job["id"])
        flow.approve(job["id"], "Synthetic test fixture owner review")
        checks = await verify_accounts(flow)
        assert checks["youtube"]["status"] == "verified"
        assert (await flow.publish(job["id"]))["state"] == "published"
        assert (await flow.collect_metrics(job["id"]))["provider_metrics"] == {"views": 42}
        assert sum(request.url.host == "oauth2.googleapis.com" for request in requests) == 1
        assert sum(request.method == "PUT" for request in requests) == 1
        persisted = json.dumps({kind: flow.store.list(kind) for kind in ("campaign", "job", "metrics", "account_check")})
        assert all(secret not in persisted for secret in ("private-client", "private-refresh", "renewed-access", "old-unknown-expiry"))


async def test_unauthorized_read_invalidates_cache_without_automatic_retry(monkeypatch):
    class Tokens:
        invalidations = 0
        calls = 0
        async def get_access_token(self):
            self.calls += 1
            return "private-token"
        def invalidate(self):
            self.invalidations += 1
    token_provider = Tokens()
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(401, json={"error": "not_logged"})
    import pytest

    from content_rewards.integrations import IntegrationError
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        publisher = YouTubePublisher("private-token", client=client, token_provider=token_provider)
        with pytest.raises(IntegrationError):
            await publisher.verify_account()
    assert len(calls) == 1
    assert token_provider.invalidations == 1
