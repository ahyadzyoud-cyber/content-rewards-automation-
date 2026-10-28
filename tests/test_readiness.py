"""Reports distinguish development checks, configuration and live provider proof."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from content_rewards.config import Settings
from content_rewards.integrations import IntegrationError
from content_rewards.readiness import (
    preflight,
    readiness,
    verify_accounts,
    write_readiness,
)
from content_rewards.service import Blocked, Workflow


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    config = Settings(database=tmp_path / "readiness.sqlite", media_root=tmp_path / "media",
                      live_publishing=True, admin_token="admin-readiness-sensitive",
                      youtube_token="youtube-readiness-sensitive", youtube_channel_id="channel-test",
                      google_client_id="client-test", google_client_secret="google-readiness-sensitive",
                      youtube_refresh_token="refresh-readiness-sensitive",
                      instagram_token="instagram-readiness-sensitive", instagram_account_id="instagram-test",
                      instagram_api_version="v24.0", instagram_media_host="media.example.com")

    def fake_render(source, output, **kwargs):
        assert kwargs["rights_verified"]
        Path(output).write_bytes(b"readiness-rendered-mp4")

    monkeypatch.setattr("content_rewards.service.render_short", fake_render)
    return Workflow(config)


def import_fixture(workflow, tmp_path, **changes):
    """All business evidence in this helper exists only in a temporary test DB."""
    source = tmp_path / "licensed-test-source.mp4"
    source.write_bytes(b"test-approved-source")
    campaign = {
        "id": "temporary-test-campaign", "title": "Test campaign only", "source": "manual",
        "source_url": "https://example.com/campaign/temporary-test",
        "rate_per_1000_views_usd": 10, "remaining_budget_usd": 1000,
        "competition_entries": 10, "eligible_countries": ["JO"],
        "eligibility_verified": True, "eligibility_evidence": "Test fixture allows Jordan creators",
        "allowed_platforms": ["youtube", "instagram"], "allows_new_accounts": True,
        "requirements": ["Review disclosure and attribution"], "requirements_verified": True,
        "rights_verified": True, "materials": [str(source)],
        "evidence_checked_at": datetime.now(UTC).isoformat(),
    } | changes
    workflow.import_campaigns([campaign])
    return campaign


def identity_record(workflow, platform, *, account_id=None, checked_at=None, status="verified"):
    expected = workflow.settings.youtube_channel_id if platform == "youtube" else workflow.settings.instagram_account_id
    workflow.store.put("account_check", platform, {
        "platform": platform, "status": status,
        "account_id": expected if account_id is None else account_id,
        "checked_at": checked_at or datetime.now(UTC).isoformat(),
        "operation": "read_only_identity",
    })


def rendered_job(workflow, tmp_path):
    campaign = import_fixture(workflow, tmp_path)
    job = workflow.plan(campaign["id"], "youtube", Path(campaign["materials"][0]),
                        "Review this actual test title", "Disclosure test caption")
    return workflow.render(job["id"])


def test_empty_readiness_does_not_invent_real_campaigns_or_live_business(workflow):
    report = readiness(workflow)
    assert report["business_live"] is False
    assert report["campaigns"]["observed"] == 0
    assert report["campaigns"]["official_live_discovery_verified"] is False
    for selection in report["campaigns"]["selections"].values():
        assert selection == {"eligible_candidates": 0, "best": None}
    assert report["publication"]["confirmed_jobs"] == 0
    assert report["publication"]["jobs_with_metrics"] == 0
    codes = {item["code"] for item in report["required_actions"]}
    assert {"campaign_access_youtube", "campaign_access_instagram", "first_publication",
            "tracking", "production_execution"} <= codes


def test_configured_tokens_are_not_live_account_verification_and_never_leak(workflow):
    report = readiness(workflow)
    for account in report["accounts"].values():
        assert account["configured"] is True
        assert account["identity_read_verified"] is False
    encoded = json.dumps(report)
    for sensitive in ("admin-readiness-sensitive", "youtube-readiness-sensitive",
                      "google-readiness-sensitive", "refresh-readiness-sensitive",
                      "instagram-readiness-sensitive", "channel-test", "instagram-test"):
        assert sensitive not in encoded


@pytest.mark.parametrize("status,account_id,age,expected", [
    ("verified", "channel-test", timedelta(minutes=1), True),
    ("verified", "different-channel", timedelta(minutes=1), False),
    ("blocked", "channel-test", timedelta(minutes=1), False),
    ("verified", "channel-test", timedelta(days=1, seconds=1), False),
    ("verified", "channel-test", timedelta(minutes=-1), False),
])
def test_only_matching_fresh_account_identity_is_reported_verified(workflow, status, account_id, age, expected):
    checked_at = (datetime.now(UTC) - age).isoformat()
    identity_record(workflow, "youtube", account_id=account_id, checked_at=checked_at, status=status)
    report = readiness(workflow)
    assert report["accounts"]["youtube"]["identity_read_verified"] is expected
    assert report["accounts"]["instagram"]["identity_read_verified"] is False


@pytest.mark.parametrize("timestamp", ["not-a-date", "2026-10-28T12:00:00", ""])
def test_malformed_or_naive_identity_timestamp_does_not_establish_readiness(workflow, timestamp):
    identity_record(workflow, "youtube")
    record = workflow.store.get("account_check", "youtube")
    record["checked_at"] = timestamp
    workflow.store.put("account_check", "youtube", record)
    assert not readiness(workflow)["accounts"]["youtube"]["identity_read_verified"]


def test_empty_account_identity_is_never_considered_verified(workflow):
    workflow.settings.youtube_channel_id = ""
    identity_record(workflow, "youtube", account_id="")
    assert not readiness(workflow)["accounts"]["youtube"]["identity_read_verified"]


def test_positive_local_records_still_do_not_claim_business_is_live(workflow, tmp_path):
    campaign = import_fixture(workflow, tmp_path)
    identity_record(workflow, "youtube")
    identity_record(workflow, "instagram")
    workflow.store.put("job", "test-published", {"id": "test-published", "state": "published"})
    workflow.store.put("metrics", "test-published", {"job_id": "test-published", "provider_metrics": {"views": 100}})
    report = readiness(workflow)
    assert report["campaigns"]["selections"]["youtube"]["best"]["campaign_id"] == campaign["id"]
    assert report["accounts"]["youtube"]["identity_read_verified"]
    assert report["publication"]["confirmed_jobs"] == report["publication"]["jobs_with_metrics"] == 1
    assert report["business_live"] is False
    assert report["campaigns"]["official_live_discovery_verified"] is False
    assert "production_execution" in {item["code"] for item in report["required_actions"]}


def test_untrusted_feed_cannot_self_verify_payout_eligibility(workflow, tmp_path):
    campaign = import_fixture(workflow, tmp_path, payout_eligibility_verified=True,
                              payout_evidence="Feed claims a verified payout account")
    workflow.import_campaigns([campaign], untrusted_feed=True)
    record = workflow.store.get("campaign", campaign["id"])
    assert record["payout_eligibility_verified"] is False


async def test_verify_accounts_records_only_successful_read_only_identity_checks(workflow, monkeypatch):
    calls = []

    class IdentityReader:
        def __init__(self, platform):
            self.platform = platform

        async def verify_account(self):
            calls.append(self.platform)
            return {"id": "channel-test" if self.platform == "youtube" else "instagram-test"}

    async def publisher(platform):
        return IdentityReader(platform)

    monkeypatch.setattr(workflow, "_publisher", publisher)
    result = await verify_accounts(workflow)
    assert calls == ["youtube", "instagram"]
    for platform in calls:
        assert result[platform] == {"status": "verified", "operation": "read_only_identity"}
        record = workflow.store.get("account_check", platform)
        assert record["status"] == "verified"
        assert record["operation"] == "read_only_identity"
    assert readiness(workflow)["accounts"]["youtube"]["identity_read_verified"]
    assert "readiness-sensitive" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["mismatch", "blocked", "integration_error"])
async def test_failed_or_mismatched_verification_clears_prior_success(workflow, monkeypatch, failure):
    identity_record(workflow, "youtube")
    identity_record(workflow, "instagram")

    class FailingReader:
        async def verify_account(self):
            if failure == "mismatch":
                return {"id": "not-the-configured-owner"}
            if failure == "blocked":
                raise Blocked("Sensitive upstream information must not be persisted")
            raise IntegrationError("Sensitive upstream information must not be persisted")

    async def publisher(platform):
        return FailingReader()

    monkeypatch.setattr(workflow, "_publisher", publisher)
    result = await verify_accounts(workflow)
    for platform in ("youtube", "instagram"):
        assert result[platform]["status"] == "blocked"
        record = workflow.store.get("account_check", platform)
        assert record["status"] == "blocked"
        assert "account_id" not in record
        assert not readiness(workflow)["accounts"][platform]["identity_read_verified"]
    assert "Sensitive upstream" not in json.dumps(result)
    assert "Sensitive upstream" not in json.dumps(workflow.store.list("account_check"))


def test_preflight_is_a_local_non_approving_review_packet(workflow, tmp_path, monkeypatch):
    job = rendered_job(workflow, tmp_path)
    before_job = workflow.store.get("job", job["id"])
    before_campaign = workflow.store.get("campaign", job["campaign_id"])
    source_bytes = Path(job["source_path"]).read_bytes()
    inspected = []

    def inspect(path):
        inspected.append(path)
        return {"width": 1080, "height": 1920, "duration_seconds": 30,
                "video_codec": "h264", "audio_codec": "aac"}

    def forbidden(*args, **kwargs):
        pytest.fail("Preflight must not authorize, publish, create network clients or change media")

    monkeypatch.setattr("content_rewards.readiness.inspect_video", inspect)
    monkeypatch.setattr(workflow, "approve", forbidden)
    monkeypatch.setattr(workflow, "_publisher", forbidden)
    monkeypatch.setattr("httpx.AsyncClient", forbidden)
    report = preflight(workflow, job["id"])
    assert inspected == [Path(job["media_path"]) ]
    assert report["campaign_id"] == job["campaign_id"]
    assert report["campaign_source_url"] == before_campaign["source_url"]
    assert report["title"] == job["title"]
    assert report["caption"] == job["caption"]
    assert report["media_sha256"] == job["media_sha256"]
    assert report["external_writes"] is False
    assert report["approved_by_this_check"] is False
    assert report["campaign_submission_verified"] is False
    assert report["payout_verified"] is False
    blockers = " ".join(report["blockers"]).lower()
    for needed in ("approval", "payout", "qualifying", "deadline"):
        assert needed in blockers
    assert workflow.store.get("job", job["id"]) == before_job
    assert workflow.store.get("campaign", job["campaign_id"]) == before_campaign
    assert Path(job["source_path"]).read_bytes() == source_bytes
    assert "readiness-sensitive" not in json.dumps(report)


def test_preflight_requires_matching_fresh_account_proof_not_just_configured_token(workflow, tmp_path, monkeypatch):
    job = rendered_job(workflow, tmp_path)
    monkeypatch.setattr("content_rewards.readiness.inspect_video", lambda path: {"video_codec": "h264"})
    report = preflight(workflow, job["id"])
    assert any("identity" in reason.lower() or "verify-accounts" in reason.lower()
               for reason in report["blockers"])
    identity_record(workflow, "youtube")
    verified = preflight(workflow, job["id"])
    assert not any("identity" in reason.lower() or "verify-accounts" in reason.lower()
                   for reason in verified["blockers"])


def test_preflight_detects_changed_or_missing_render_without_repairing_it(workflow, tmp_path, monkeypatch):
    job = rendered_job(workflow, tmp_path)
    monkeypatch.setattr("content_rewards.readiness.inspect_video", lambda path: {"video_codec": "h264"})
    Path(job["media_path"]).write_bytes(b"changed-media")
    assert any("differs" in reason for reason in preflight(workflow, job["id"])["blockers"])
    Path(job["media_path"]).unlink()
    assert any("missing" in reason for reason in preflight(workflow, job["id"])["blockers"])
    assert workflow.store.get("job", job["id"])["state"] == "rendered"


def test_write_readiness_saves_current_report_without_touching_business_records(workflow, tmp_path):
    destination = tmp_path / "reports" / "readiness.json"
    write_readiness(workflow, destination)
    report = json.loads(destination.read_text())
    assert report["business_live"] is False
    assert report["campaigns"]["observed"] == 0
    assert workflow.store.list("campaign") == []
    assert workflow.store.list("job") == []
    assert "readiness-sensitive" not in destination.read_text()
