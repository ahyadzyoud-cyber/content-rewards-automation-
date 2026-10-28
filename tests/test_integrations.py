from pathlib import Path

import httpx
import pytest

from content_rewards.integrations import (
    EvidenceFeed,
    IndeterminatePublishError,
    InstagramPublisher,
    IntegrationError,
    YouTubePublisher,
)


@pytest.mark.asyncio
async def test_youtube_resumable_upload_streams_video_privately(tmp_path: Path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"test-mp4-content")
    requests = []

    async def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"
        assert "test-token" not in str(request.url)
        if request.method == "POST":
            import json
            body = json.loads(request.content)
            assert body["status"]["privacyStatus"] == "private"
            assert body["snippet"]["title"] == "Title"
            assert request.url.params["uploadType"] == "resumable"
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=123"})
        assert request.method == "PUT"
        assert await request.aread() == video.read_bytes()
        assert request.headers["Content-Length"] == str(video.stat().st_size)
        return httpx.Response(200, json={"id": "video_123"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await YouTubePublisher("test-token", client).upload(video, "Title", "Description") == "video_123"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_upload_rejects_untrusted_session_host(tmp_path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"test")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, headers={"Location": "https://attacker.example/upload"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IntegrationError, match="configured provider host"):
            await YouTubePublisher("secret-token", client).upload(video, "Title", "")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_upload_unknown_outcome_is_not_retried(tmp_path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"test")
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=123"})
        raise httpx.ReadTimeout("secret-token appeared in an upstream message")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IndeterminatePublishError) as error:
            await YouTubePublisher("secret-token", client).upload(video, "Title", "")
    assert "secret-token" not in str(error.value)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_youtube_metrics_and_channel_verification():
    def handler(request):
        if request.url.path.endswith("channels"):
            assert request.url.params["mine"] == "true"
            return httpx.Response(200, json={"items": [{"id": "channel1", "status": {"isLinked": True}}]})
        return httpx.Response(200, json={"items": [{"statistics": {"viewCount": "123", "likeCount": "2"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        publisher = YouTubePublisher("test-token", client)
        assert (await publisher.verify_account())["id"] == "channel1"
        assert await publisher.metrics("video_1") == {"views": 123, "likes": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"items": []}, {"items": [{"statistics": {}}]}, {"items": [{"statistics": {"viewCount": "invalid"}}]}])
async def test_unavailable_youtube_metrics_are_not_reported_as_zero(payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(IntegrationError):
            await YouTubePublisher("test-token", client).metrics("video_1")


@pytest.mark.asyncio
async def test_errors_never_echo_provider_body_or_token():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "secret-token in debug message"}))) as client:
        with pytest.raises(IntegrationError, match="HTTP 401") as error:
            await YouTubePublisher("secret-token", client).verify_account()
    assert "secret-token" not in str(error.value)


@pytest.mark.asyncio
async def test_instagram_container_status_and_publish_are_separate():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"
        assert "test-token" not in str(request.url)
        assert request.url.host == "graph.instagram.com"
        assert request.url.path.startswith("/v24.0/")
        if request.url.path.endswith("/media"):
            assert b"media_type=REELS" in request.content
            assert b"video_url=" in request.content
            return httpx.Response(200, json={"id": "container1"})
        if request.url.path.endswith("/media_publish"):
            assert request.content == b"creation_id=container1"
            return httpx.Response(200, json={"id": "published1"})
        return httpx.Response(200, json={"status_code": "FINISHED"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        publisher = InstagramPublisher("test-token", "account1", "v24.0", client)
        assert await publisher.create_container("https://assets.example.com/short.mp4", "Caption") == "container1"
        assert len(calls) == 1  # Preparing a container never publishes implicitly.
        assert await publisher.container_status("container1") == "FINISHED"
        assert await publisher.publish_container("container1") == "published1"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_instagram_publish_500_is_ambiguous_and_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text="sensitive provider body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IndeterminatePublishError, match="reconcile"):
            await InstagramPublisher("test-token", "account1", "v24.0", client).publish_container("container1")
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"user_id": "other", "account_type": "Business"},
    {"user_id": "account1", "account_type": "PERSONAL"},
    {"id": "account1", "account_type": "Business"},
    {"id": "account1", "user_id": "other", "account_type": "Business"},
    {"user_id": "account1", "account_type": "CREATOR"},
    {"user_id": True, "account_type": "Business"},
    {"user_id": "account1", "account_type": None},
    {"data": []},
    {"data": [{"user_id": "account1", "account_type": "Business"},
              {"user_id": "other", "account_type": "Business"}]},
    {"data": {"user_id": "account1", "account_type": "Business"}},
    {"data": ["invalid"]},
])
async def test_instagram_account_verification_requires_matching_professional_account(payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(IntegrationError):
            await InstagramPublisher("test-token", "account1", "v24.0", client).verify_account()


@pytest.mark.asyncio
@pytest.mark.parametrize("account_type", ["Business", "Media_Creator", "BUSINESS", "MEDIA_CREATOR"])
@pytest.mark.parametrize("wrapped", [False, True])
async def test_instagram_identity_uses_token_professional_user_id(account_type, wrapped):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/v26.0/me"
        assert dict(request.url.params) == {"fields": "user_id,username,account_type"}
        assert request.headers["Authorization"] == "Bearer test-token"
        assert "test-token" not in str(request.url)
        account = {"id": "different-app-scoped-id", "user_id": "account1", "username": "creator",
                   "account_type": account_type}
        return httpx.Response(200, json={"data": [account]} if wrapped else account)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await InstagramPublisher("test-token", "account1", "v26.0", client).verify_account()
    assert result == {"id": "account1", "user_id": "account1", "username": "creator",
                      "account_type": account_type.upper()}


@pytest.mark.asyncio
async def test_instagram_identity_accepts_numeric_professional_id():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"user_id": 12345, "account_type": "Business"}))) as client:
        account = await InstagramPublisher("test-token", "12345", "v26.0", client).verify_account()
    assert account["id"] == "12345"


@pytest.mark.asyncio
async def test_instagram_missing_views_fails_and_never_fabricates_earnings():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))) as client:
        with pytest.raises(IntegrationError, match="view insights"):
            await InstagramPublisher("test-token", "account1", "v24.0", client).metrics("media1")


@pytest.mark.asyncio
async def test_instagram_insights_mapping():
    payload = {"data": [{"name": "views", "values": [{"value": 134}]}, {"name": "likes", "values": [{"value": 7}]}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        assert await InstagramPublisher("test-token", "account1", "v24.0", client).metrics("media1") == {"views": 134, "likes": 7}


@pytest.mark.parametrize("url", ["http://assets.example.com/video.mp4", "https://localhost/video.mp4", "https://127.0.0.1/video.mp4", "https://user:password@assets.example.com/video.mp4", "https://assets.example.com:8443/video.mp4"])
@pytest.mark.asyncio
async def test_instagram_rejects_nonpublic_video_urls(url):
    def unexpected(_):
        pytest.fail("Invalid URLs must fail before any HTTP request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(IntegrationError):
            await InstagramPublisher("test-token", "account1", "v24.0", client).create_container(url, "Caption")


@pytest.mark.asyncio
async def test_feed_never_self_verifies_campaigns():
    payload = {"campaigns": [{"id": "one", "eligibility_verified": True, "requirements_verified": True, "rights_verified": True, "evidence_checked_at": "2026-10-28T00:00:00Z"}]}

    def handler(request):
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        campaigns = await EvidenceFeed("campaigns.example.com", client).fetch("https://campaigns.example.com/feed.json")
    assert campaigns[0]["eligibility_verified"] is False
    assert campaigns[0]["requirements_verified"] is False
    assert campaigns[0]["rights_verified"] is False
    assert campaigns[0]["evidence_checked_at"] is None


@pytest.mark.asyncio
async def test_feed_does_not_follow_redirect_or_allow_another_host():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.com/secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        feed = EvidenceFeed("campaigns.example.com", client)
        with pytest.raises(IntegrationError, match="HTTP 302"):
            await feed.fetch("https://campaigns.example.com/feed.json")
        with pytest.raises(IntegrationError, match="configured provider host"):
            await feed.fetch("https://other.example.com/feed.json")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_feed_has_bounded_payload_size():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 2_000_001))) as client:
        with pytest.raises(IntegrationError, match="size limit"):
            await EvidenceFeed("campaigns.example.com", client).fetch("https://campaigns.example.com/feed.json")


def test_tokens_and_versions_are_required():
    with pytest.raises(IntegrationError, match="authorized access token"):
        YouTubePublisher("")
    with pytest.raises(IntegrationError, match="API version"):
        InstagramPublisher("test-token", "account1", "latest")
