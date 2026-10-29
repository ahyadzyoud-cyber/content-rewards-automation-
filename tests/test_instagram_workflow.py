"""Instagram approval binds public media bytes, account and campaign evidence."""

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from content_rewards import feeds
from content_rewards.config import Settings
from content_rewards.integrations import IntegrationError
from content_rewards.service import Blocked, Workflow

RENDERED = b"test-rendered-instagram-video"


class FakeInstagram:
    def __init__(self):
        self.calls = []

    async def verify_account(self):
        self.calls.append("verify")
        return {"id": "instagram-account"}

    async def require_publishing_capacity(self):
        self.calls.append("capacity")

    async def create_container(self, video_url, caption):
        self.calls.append("create")
        assert video_url.startswith("https://media.example.com/")
        assert caption == "Approved caption"
        return "container1"

    async def container_status(self, container_id):
        self.calls.append("status")
        assert container_id == "container1"
        return "FINISHED"

    async def publish_container(self, container_id):
        self.calls.append("publish")
        assert container_id == "container1"
        return "instagram-media"


@pytest.fixture
def instagram_workflow(tmp_path, monkeypatch):
    settings = Settings(
        database=tmp_path / "instagram.sqlite", media_root=tmp_path / "media", live_publishing=True,
        instagram_account_id="instagram-account", instagram_api_version="v24.0",
        instagram_media_host="media.example.com", instagram_token="test-token",
    )

    def render(source, output, **kwargs):
        assert kwargs["rights_verified"] is True
        Path(output).write_bytes(RENDERED)

    monkeypatch.setattr("content_rewards.service.render_short", render)
    workflow = Workflow(settings)
    source = tmp_path / "approved.mp4"
    source.write_bytes(b"approved-campaign-material")
    workflow.import_campaigns([{
        "id": "instagram-campaign", "title": "Verified Instagram campaign", "source": "manual",
        "source_url": "https://example.com/campaign", "rate_per_1000_views_usd": 5,
        "remaining_budget_usd": 1000, "competition_entries": 10, "eligible_countries": ["JO"],
        "eligibility_verified": True, "eligibility_evidence": "Fixture explicitly allows Jordan and new accounts",
        "allowed_platforms": ["instagram"], "allows_new_accounts": True,
        "requirements_verified": True, "rights_verified": True, "materials": [str(source)],
        "evidence_checked_at": datetime.now(UTC).isoformat(),
    }])
    job = workflow.plan("instagram-campaign", "instagram", source, "Approved title", "Approved caption")
    return workflow, workflow.render(job["id"])


def approve(workflow, job):
    return workflow.approve(job["id"], "Owner reviewed this exact clip and target", video_url=f"https://media.example.com/{job['media_sha256']}.mp4")


def mock_hosted_media(monkeypatch, *, body=RENDERED, content_type="video/mp4", status=200):
    monkeypatch.setattr(feeds.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
    ])
    requests = []
    original_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "media.example.com"
        assert "Authorization" not in request.headers
        return httpx.Response(status, content=body, headers={"Content-Type": content_type})

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("content_rewards.service.httpx.AsyncClient", factory)
    return requests


async def test_exact_hosted_bytes_verified_before_container_and_publish_once(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approved = approve(workflow, job)
    requests = mock_hosted_media(monkeypatch)
    publisher = FakeInstagram()
    result = await workflow.publish(job["id"], publisher)
    assert result["state"] == "published"
    assert result["remote_id"] == "instagram-media"
    assert result["container_id"] == "container1"
    assert publisher.calls == ["verify", "capacity", "create", "status", "capacity", "publish"]
    assert len(requests) == 1
    assert str(requests[0].url) == approved["video_url"]
    with pytest.raises(Blocked, match="requires approval"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls.count("publish") == 1


async def test_hosted_bytes_mismatch_blocks_all_external_writes(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch, body=b"different-video")
    publisher = FakeInstagram()
    with pytest.raises(Blocked, match="differs from the approved video"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == ["verify"]
    assert workflow.store.get("job", job["id"])["state"] == "approved"


async def test_hosted_file_must_be_mp4_not_html(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch, content_type="text/html")
    publisher = FakeInstagram()
    with pytest.raises(Blocked, match="serve video/mp4"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == ["verify"]


@pytest.mark.parametrize("url", [
    "http://media.example.com/{hash}.mp4", "https://other.example.com/{hash}.mp4",
    "https://media.example.com/{hash}.mp4?token=private", "https://media.example.com/wrong-hash.mp4",
    "https://user:secret@media.example.com/{hash}.mp4", "https://media.example.com:8443/{hash}.mp4",
])
def test_approval_rejects_unapproved_host_secret_query_or_wrong_hash_path(instagram_workflow, url):
    workflow, job = instagram_workflow
    with pytest.raises(ValueError):
        workflow.approve(job["id"], "Reviewed", video_url=url.format(hash=job["media_sha256"]))
    stored = workflow.store.get("job", job["id"])
    assert stored["state"] == "rendered"
    assert stored["approval"] is None


def test_instagram_approval_requires_configured_immutable_host(instagram_workflow):
    workflow, job = instagram_workflow
    workflow.settings.instagram_media_host = ""
    with pytest.raises(Blocked, match="immutable HTTPS media host"):
        approve(workflow, job)


@pytest.mark.parametrize("mutation", ["video_url", "caption", "media", "target", "approval"])
async def test_tampered_approved_instagram_job_never_contacts_provider(instagram_workflow, mutation):
    workflow, job = instagram_workflow
    job = approve(workflow, job)
    if mutation == "media":
        Path(job["media_path"]).write_bytes(b"changed-media")
    elif mutation == "target":
        workflow.settings.instagram_account_id = "another-account"
    elif mutation == "approval":
        job["approval"]["digest"] = "tampered-digest"
        workflow.store.put("job", job["id"], job)
    else:
        job[mutation] = "https://media.example.com/changed.mp4" if mutation == "video_url" else "Changed caption"
        workflow.store.put("job", job["id"], job)
    publisher = FakeInstagram()
    with pytest.raises(Blocked, match="changed after approval"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == []


async def test_stale_campaign_evidence_blocks_an_old_instagram_approval(instagram_workflow):
    workflow, job = instagram_workflow
    approve(workflow, job)
    campaign = workflow.store.get("campaign", job["campaign_id"])
    campaign["evidence_checked_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    workflow.store.put("campaign", campaign["id"], campaign)
    publisher = FakeInstagram()
    with pytest.raises(Blocked, match="older than seven days"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == []


async def test_private_dns_prevents_hosted_media_fetch(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    monkeypatch.setattr(feeds.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
    ])
    publisher = FakeInstagram()
    with pytest.raises(ValueError, match="exclusively to public"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == ["verify"]


async def test_container_error_never_publishes_and_requires_reconciliation(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)

    class FailedContainer(FakeInstagram):
        async def container_status(self, container_id):
            self.calls.append("status")
            return "ERROR"

    publisher = FailedContainer()
    with pytest.raises(Blocked, match="uncertain"):
        await workflow.publish(job["id"], publisher)
    assert "publish" not in publisher.calls
    assert workflow.store.get("job", job["id"])["state"] == "needs_reconciliation"


async def test_in_progress_container_is_polled_before_publication(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("content_rewards.service.asyncio.sleep", fake_sleep)

    class ProcessingPublisher(FakeInstagram):
        async def container_status(self, container_id):
            self.calls.append("status")
            assert "publish" not in self.calls
            return "IN_PROGRESS" if self.calls.count("status") == 1 else "FINISHED"

    publisher = ProcessingPublisher()
    assert (await workflow.publish(job["id"], publisher))["state"] == "published"
    assert publisher.calls == ["verify", "capacity", "create", "status", "status", "capacity", "publish"]
    assert sleeps == [10]


@pytest.mark.parametrize("error", ["exhausted", "unavailable or invalid"])
async def test_capacity_blocker_before_container_leaves_approval_and_no_provider_writes(
        instagram_workflow, monkeypatch, error):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)

    class NoCapacity(FakeInstagram):
        async def require_publishing_capacity(self):
            self.calls.append("capacity")
            raise IntegrationError("Instagram publishing capacity is " + error)

    publisher = NoCapacity()
    with pytest.raises(IntegrationError, match=error):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == ["verify", "capacity"]
    assert workflow.store.get("job", job["id"])["state"] == "approved"


async def test_capacity_consumed_during_processing_prevents_final_publish(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)

    class CapacityConsumed(FakeInstagram):
        async def require_publishing_capacity(self):
            self.calls.append("capacity")
            if self.calls.count("capacity") == 2:
                raise IntegrationError("Instagram publishing capacity is exhausted")

    publisher = CapacityConsumed()
    with pytest.raises(Blocked, match="reconcile|uncertain"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == ["verify", "capacity", "create", "status", "capacity"]
    assert workflow.store.get("job", job["id"])["state"] == "needs_reconciliation"


async def test_revocation_during_final_capacity_check_blocks_publish(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)

    class RevokingCapacity(FakeInstagram):
        async def require_publishing_capacity(self):
            self.calls.append("capacity")
            if self.calls.count("capacity") == 2:
                campaign = workflow.store.get("campaign", job["campaign_id"])
                campaign["rights_verified"] = False
                workflow.store.put("campaign", campaign["id"], campaign)

    publisher = RevokingCapacity()
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert "publish" not in publisher.calls


async def test_revocation_during_container_processing_blocks_final_publication(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)

    class RevokingPublisher(FakeInstagram):
        async def container_status(self, container_id):
            self.calls.append("status")
            campaign = workflow.store.get("campaign", job["campaign_id"])
            campaign["rights_verified"] = False
            workflow.store.put("campaign", campaign["id"], campaign)
            return "FINISHED"

    publisher = RevokingPublisher()
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert "publish" not in publisher.calls


async def test_metadata_change_during_container_processing_blocks_final_publication(instagram_workflow, monkeypatch):
    workflow, job = instagram_workflow
    approve(workflow, job)
    mock_hosted_media(monkeypatch)

    class EditingPublisher(FakeInstagram):
        async def container_status(self, container_id):
            self.calls.append("status")
            current = workflow.store.get("job", job["id"])
            current["caption"] = "Edited after publication approval"
            workflow.store.put("job", job["id"], current)
            return "FINISHED"

    publisher = EditingPublisher()
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert "publish" not in publisher.calls
