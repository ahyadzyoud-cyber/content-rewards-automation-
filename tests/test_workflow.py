"""Durable workflow checks; fake publishers never contact external accounts."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from compliance_fixtures import publication_evidence, video_metadata
from pydantic import ValidationError

from content_rewards.config import Settings
from content_rewards.service import Blocked, Workflow
from content_rewards.store import Store


class FakePublisher:
    def __init__(self, account_id="channel-verified", *, fail_upload=False):
        self.account_id = account_id
        self.fail_upload = fail_upload
        self.uploads = 0
        self.verifications = 0

    async def verify_account(self):
        self.verifications += 1
        await asyncio.sleep(0)
        return {"id": self.account_id}

    async def upload(self, path, title, description):
        self.uploads += 1
        assert Path(path).read_bytes() == b"rendered-mp4"
        if self.fail_upload:
            raise TimeoutError("Provider response lost after upload")
        await asyncio.sleep(0)
        return "published-video"

    async def metrics(self, video_id):
        assert video_id == "published-video"
        return {"views": 2500, "likes": 20}


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    settings = Settings(database=tmp_path / "state.sqlite", media_root=tmp_path / "media",
                        live_publishing=True, youtube_channel_id="channel-verified",
                        instagram_account_id="instagram-verified")

    def fake_render(source, output, **kwargs):
        assert kwargs["rights_verified"] is True
        Path(output).write_bytes(b"rendered-mp4")

    monkeypatch.setattr("content_rewards.service.render_short", fake_render)
    monkeypatch.setattr("content_rewards.service.inspect_video", video_metadata)
    return Workflow(settings)


def campaign_record(tmp_path, **updates):
    source = tmp_path / "campaign-approved.mp4"
    if not source.exists():
        source.write_bytes(b"source-material")
    return {
        "id": "campaign-verified", "title": "Explicitly verified test campaign",
        "source": "manual", "source_url": "https://example.com/campaign",
        "rate_per_1000_views_usd": 5, "remaining_budget_usd": 1000,
        "competition_entries": 10, "eligible_countries": ["JO"],
        "eligibility_verified": True,
        "eligibility_evidence": "Test fixture: Jordan and new accounts explicitly allowed",
        "allowed_platforms": ["youtube", "instagram"], "allows_new_accounts": True,
        "requirements_verified": True, "rights_verified": True,
        "materials": [str(source)],
        "evidence_checked_at": datetime.now(UTC).isoformat(),
        **publication_evidence(),
    } | updates


def prepared_job(workflow, tmp_path, *, approve=True, platform="youtube"):
    campaign = campaign_record(tmp_path)
    workflow.import_campaigns([campaign])
    job = workflow.plan(campaign["id"], platform, Path(campaign["materials"][0]),
                        "Reviewed title", "Reviewed caption")
    workflow.render(job["id"])
    if approve:
        kwargs = {"video_url": "https://media.example.com/approved.mp4"} if platform == "instagram" else {}
        workflow.approve(job["id"], "Operator reviewed this exact rendered output", **kwargs)
    return workflow.store.get("job", job["id"])


async def test_complete_import_rank_render_approve_publish_and_restart(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)
    assert workflow.rank("youtube")[0]["selectable"]
    assert job["state"] == "approved"
    assert job["approval"]["digest"]
    publisher = FakePublisher()
    result = await workflow.publish(job["id"], publisher)
    assert result["state"] == "published"
    assert result["remote_id"] == "published-video"
    assert publisher.verifications == publisher.uploads == 1
    restarted = Workflow(workflow.settings)
    assert restarted.store.get("job", job["id"])["state"] == "published"
    with restarted.store.connect() as db:
        events = [row[0] for row in db.execute("SELECT kind FROM events ORDER BY id")]
    for required in ("campaign_import", "rendered", "publication_approved", "published"):
        assert required in events
    assert events.count("published") == 1


def test_import_validates_entire_batch_before_writing(workflow, tmp_path):
    valid = campaign_record(tmp_path)
    with pytest.raises(ValidationError):
        workflow.import_campaigns([valid, valid | {"id": "invalid", "remaining_budget_usd": -1}])
    assert workflow.store.list("campaign") == []
    with pytest.raises(ValueError, match="Duplicate"):
        workflow.import_campaigns([valid, valid])
    assert workflow.store.list("campaign") == []


def test_untrusted_feed_cannot_assert_eligibility_or_rights(workflow, tmp_path):
    workflow.import_campaigns([campaign_record(tmp_path)], untrusted_feed=True)
    record = workflow.store.get("campaign", "campaign-verified")
    assert not record["eligibility_verified"]
    assert not record["rights_verified"]
    assert not record["requirements_verified"]
    assert record["evidence_checked_at"] is None
    assert not workflow.rank()[0]["selectable"]


def test_unverified_jordan_eligibility_blocks_planning(workflow, tmp_path):
    campaign = campaign_record(tmp_path, eligible_countries=["US"])
    workflow.import_campaigns([campaign])
    with pytest.raises(Blocked, match="JO"):
        workflow.plan(campaign["id"], "youtube", Path(campaign["materials"][0]), "Title")
    assert workflow.store.list("job") == []


def test_source_must_be_campaign_approved_material(workflow, tmp_path):
    campaign = campaign_record(tmp_path)
    workflow.import_campaigns([campaign])
    other = tmp_path / "unapproved.mp4"
    other.write_bytes(b"not-approved")
    with pytest.raises(Blocked, match="approved local material"):
        workflow.plan(campaign["id"], "youtube", other, "Title")


def test_source_change_after_planning_blocks_render(workflow, tmp_path):
    campaign = campaign_record(tmp_path)
    workflow.import_campaigns([campaign])
    source = Path(campaign["materials"][0])
    job = workflow.plan(campaign["id"], "youtube", source, "Title")
    source.write_bytes(b"changed source")
    with pytest.raises(Blocked, match="source changed"):
        workflow.render(job["id"])
    assert workflow.store.get("job", job["id"])["state"] == "planned"


def test_revoked_material_cannot_be_rendered_from_an_old_plan(workflow, tmp_path):
    campaign = campaign_record(tmp_path)
    workflow.import_campaigns([campaign])
    source = Path(campaign["materials"][0])
    job = workflow.plan(campaign["id"], "youtube", source, "Title")
    replacement = tmp_path / "replacement-approved.mp4"
    replacement.write_bytes(b"replacement material")
    workflow.import_campaigns([campaign | {"materials": [str(replacement)]}])
    with pytest.raises(Blocked, match="material"):
        workflow.render(job["id"])
    assert workflow.store.get("job", job["id"])["state"] == "planned"


def test_approval_requires_rendered_output_target_and_reason(workflow, tmp_path):
    campaign = campaign_record(tmp_path)
    workflow.import_campaigns([campaign])
    job = workflow.plan(campaign["id"], "youtube", Path(campaign["materials"][0]), "Title")
    with pytest.raises(Blocked, match="rendered"):
        workflow.approve(job["id"], "Reviewed")
    workflow.render(job["id"])
    with pytest.raises(Blocked, match="review reason"):
        workflow.approve(job["id"], "  ")
    workflow.settings.youtube_channel_id = ""
    with pytest.raises(Blocked, match="target account"):
        workflow.approve(job["id"], "Reviewed")


def test_tampered_render_cannot_be_approved(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path, approve=False)
    Path(job["media_path"]).write_bytes(b"tampered bytes")
    with pytest.raises(Blocked, match="Rendered file changed"):
        workflow.approve(job["id"], "Reviewed")


@pytest.mark.parametrize("mutation", ["media", "caption", "title", "campaign", "target", "video_url"])
async def test_approval_is_bound_to_media_metadata_evidence_and_target(workflow, tmp_path, mutation):
    job = prepared_job(workflow, tmp_path)
    if mutation == "media":
        Path(job["media_path"]).write_bytes(b"tampered")
    elif mutation == "campaign":
        campaign = workflow.store.get("campaign", job["campaign_id"])
        campaign["requirements"].append("Changed terms")
        workflow.store.put("campaign", job["campaign_id"], campaign)
    elif mutation == "target":
        workflow.settings.youtube_channel_id = "different-channel"
    else:
        job[mutation] = "Changed after approval"
        workflow.store.put("job", job["id"], job)
    publisher = FakePublisher()
    with pytest.raises(Blocked, match="changed after approval"):
        await workflow.publish(job["id"], publisher)
    assert publisher.uploads == 0
    assert workflow.store.get("job", job["id"])["state"] == "approved"


async def test_publishing_disabled_by_default_even_with_approval(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)
    workflow.settings.live_publishing = False
    publisher = FakePublisher()
    with pytest.raises(Blocked, match="disabled"):
        await workflow.publish(job["id"], publisher)
    assert publisher.verifications == publisher.uploads == 0


async def test_account_verification_must_match_approved_target(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)
    publisher = FakePublisher(account_id="another-channel")
    with pytest.raises(Blocked, match="does not match"):
        await workflow.publish(job["id"], publisher)
    assert publisher.uploads == 0
    assert workflow.store.get("job", job["id"])["state"] == "approved"


async def test_campaign_mutation_during_account_verification_blocks_external_write(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)

    class MutatingPublisher(FakePublisher):
        async def verify_account(self):
            account = await super().verify_account()
            campaign = workflow.store.get("campaign", job["campaign_id"])
            campaign["rights_verified"] = False
            workflow.store.put("campaign", job["campaign_id"], campaign)
            return account

    publisher = MutatingPublisher()
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert publisher.uploads == 0
    assert workflow.store.get("job", job["id"])["state"] == "approved"


async def test_job_mutation_during_account_verification_cannot_be_overwritten_by_stale_claim(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)

    class MutatingPublisher(FakePublisher):
        async def verify_account(self):
            account = await super().verify_account()
            changed = workflow.store.get("job", job["id"])
            changed["caption"] = "Concurrent edit requiring new approval"
            workflow.store.put("job", job["id"], changed)
            return account

    publisher = MutatingPublisher()
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert publisher.uploads == 0
    assert workflow.store.get("job", job["id"])["caption"] == "Concurrent edit requiring new approval"


async def test_unapproved_render_cannot_be_published(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path, approve=False)
    publisher = FakePublisher()
    with pytest.raises(Blocked, match="requires approval"):
        await workflow.publish(job["id"], publisher)
    assert publisher.uploads == 0


async def test_duplicate_and_concurrent_publish_upload_only_once(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)
    publisher = FakePublisher()
    results = await asyncio.gather(workflow.publish(job["id"], publisher),
                                   workflow.publish(job["id"], publisher), return_exceptions=True)
    assert sum(isinstance(result, Blocked) for result in results) == 1
    assert sum(isinstance(result, dict) and result["state"] == "published" for result in results) == 1
    assert publisher.uploads == 1
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert publisher.uploads == 1


async def test_ambiguous_external_write_cannot_be_automatically_retried(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)
    publisher = FakePublisher(fail_upload=True)
    with pytest.raises(Blocked, match="uncertain"):
        await workflow.publish(job["id"], publisher)
    assert workflow.store.get("job", job["id"])["state"] == "needs_reconciliation"
    restarted = Workflow(workflow.settings)
    with pytest.raises(Blocked, match="requires approval"):
        await restarted.publish(job["id"], publisher)
    assert publisher.uploads == 1


async def test_metrics_and_verified_campaign_earnings_are_separate(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path)
    publisher = FakePublisher()
    with pytest.raises(Blocked, match="published"):
        await workflow.collect_metrics(job["id"], publisher)
    await workflow.publish(job["id"], publisher)
    metrics = await workflow.collect_metrics(job["id"], publisher)
    assert metrics["provider_metrics"] == {"views": 2500, "likes": 20}
    assert "earnings_usd" not in metrics
    assert workflow.store.list("submission") == []
    with pytest.raises(Blocked, match="verified approved or paid"):
        workflow.record_submission(job["id"], "submitted", "https://example.com/submission", 100)
    record = workflow.record_submission(job["id"], "approved", "https://example.com/submission", 12.5)
    assert record["earnings_usd"] == 12.5
    assert record["verification"] == "operator_recorded"
    assert workflow.store.get("metrics", job["id"])["provider_metrics"]["views"] == 2500


@pytest.mark.parametrize("earnings", [-1, float("nan"), float("inf")])
def test_invalid_earnings_are_rejected_without_storage(workflow, tmp_path, earnings):
    job = prepared_job(workflow, tmp_path)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        workflow.record_submission(job["id"], "paid", "https://example.com/submission", earnings)
    assert workflow.store.list("submission") == []


def test_scheduler_claims_are_atomic_across_workers_and_survive_restart(workflow):
    now = 1000.0
    workflow.store.schedule("ranking", "rank", 60, {}, now)
    workflow.store.schedule("ranking", "rank", 60, {}, now)  # repeat setup is idempotent

    def claim(_):
        return Store(workflow.settings.database).claim_due(now)

    with ThreadPoolExecutor(max_workers=4) as executor:
        claims = list(executor.map(claim, range(4)))
    assert sum(len(result) for result in claims) == 1
    winner = next(result[0] for result in claims if result)
    restarted = Store(workflow.settings.database)
    assert restarted.claim_due(now + 10) == []
    reclaimed = restarted.claim_due(now + 1801)
    assert len(reclaimed) == 1
    assert reclaimed[0]["lease_token"] != winner["lease_token"]
    # The previous process finishing late must not clear the new process's lease.
    restarted.finish_schedule("ranking", winner["lease_token"], now + 1802)
    assert restarted.claim_due(now + 1803) == []
    restarted.finish_schedule("ranking", reclaimed[0]["lease_token"], now + 1804)
    assert restarted.claim_due(now + 1805) == []
    assert len(restarted.claim_due(now + 1864)) == 1


async def test_tick_records_success_and_blocked_publication_without_stopping_other_jobs(workflow, tmp_path):
    job = prepared_job(workflow, tmp_path, approve=False)
    now = 1000.0
    workflow.store.schedule("ranking", "rank", 60, {}, now)
    workflow.store.schedule("publish", "publish", 60, {"job_id": job["id"]}, now)
    results = await workflow.tick(now)
    assert {row["id"]: row["status"] for row in results} == {"ranking": "completed", "publish": "blocked"}
    report = workflow.store.get("report", "ranking")
    assert report["ranking"][0]["campaign_id"] == "campaign-verified"
    assert await Workflow(workflow.settings).tick(now + 59) == []
    assert len(await workflow.tick(now + 60)) == 2
    with workflow.store.connect() as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM events WHERE kind='schedule_run'")]
    assert len(events) == 4
    assert all("error" not in event for event in events)


def test_settings_status_exposes_presence_without_credentials(tmp_path):
    settings = Settings(database=tmp_path / "db", youtube_token="youtube-sensitive-token",
                        youtube_channel_id="channel", instagram_token="instagram-sensitive-token",
                        instagram_account_id="account", instagram_api_version="v23.0",
                        admin_token="admin-sensitive-token", live_publishing=False)
    assert settings.credential_status() == {"youtube": True, "instagram": True, "api_auth": True,
                                           "live_publishing": False}
    assert "sensitive-token" not in repr(settings)


def test_prepare_best_selects_and_renders_best_verified_campaign(workflow, tmp_path):
    lower = campaign_record(tmp_path, id="lower", rate_per_1000_views_usd=1,
                            remaining_budget_usd=10)
    best = campaign_record(tmp_path, id="best", title="Best verified campaign",
                           rate_per_1000_views_usd=50, remaining_budget_usd=10000)
    unverified = campaign_record(tmp_path, id="unverified", rate_per_1000_views_usd=10000,
                                 remaining_budget_usd=1000000, competition_entries=0,
                                 eligibility_verified=False)
    workflow.import_campaigns([lower, unverified, best])
    workflow.settings.live_publishing = False
    job = workflow.prepare_best("youtube")
    assert job["campaign_id"] == "best"
    assert job["platform"] == "youtube"
    assert job["title"] == "Best verified campaign"
    assert job["state"] == "rendered"
    assert Path(job["media_path"]).read_bytes() == b"rendered-mp4"
    assert job["approval"] is None
    assert job["remote_id"] is None


def test_prepare_best_skips_missing_and_url_only_materials(workflow, tmp_path):
    missing = campaign_record(tmp_path, id="missing", rate_per_1000_views_usd=100,
                              materials=[str(tmp_path / "does-not-exist.mp4")])
    remote = campaign_record(tmp_path, id="remote", rate_per_1000_views_usd=100,
                             materials=["https://media.example.com/campaign-approved.mp4"])
    valid = campaign_record(tmp_path, id="local", rate_per_1000_views_usd=1)
    workflow.import_campaigns([missing, remote, valid])
    job = workflow.prepare_best("youtube")
    assert job["campaign_id"] == "local"
    assert len(workflow.store.list("job")) == 1


def test_prepare_best_deduplicates_campaign_platform_but_allows_other_platform(workflow, tmp_path):
    workflow.import_campaigns([campaign_record(tmp_path)])
    first = workflow.prepare_best("youtube")
    with pytest.raises(Blocked, match="already have candidates"):
        workflow.prepare_best("youtube")
    second = workflow.prepare_best("instagram")
    assert second["id"] != first["id"]
    assert second["campaign_id"] == first["campaign_id"]
    assert second["platform"] == "instagram"
    assert second["state"] == "rendered"
    assert len(workflow.store.list("job")) == 2


def test_prepare_best_blocks_when_no_verified_eligible_campaign_exists(workflow, tmp_path):
    workflow.import_campaigns([campaign_record(tmp_path, eligibility_verified=False)])
    with pytest.raises(Blocked, match="No verified eligible campaign"):
        workflow.prepare_best("youtube")
    assert workflow.store.list("job") == []


def test_prepare_uses_reviewed_duration_and_literal_required_metadata(workflow, tmp_path, monkeypatch):
    campaign = campaign_record(tmp_path)
    for requirement in campaign["publication_spec"]["requirements"]:
        if requirement["id"] == "duration":
            requirement.update(minimum=45.0, maximum=55.0)
        elif requirement["id"] == "title":
            requirement.update(status="verified", check="title_contains", values=["Approved headline"])
        elif requirement["id"] == "caption":
            requirement.update(status="verified", check="caption_contains", values=["Paid promotion"])
        elif requirement["id"] == "hashtags":
            requirement.update(status="verified", check="hashtags", values=["#Approved"])
        elif requirement["id"] == "mentions":
            requirement.update(status="verified", check="mentions", values=["@brand.account"])
    workflow.import_campaigns([campaign])
    measured = []

    def render(source, output, **kwargs):
        measured.append(kwargs["duration_seconds"])
        Path(output).write_bytes(b"rendered-mp4")

    monkeypatch.setattr("content_rewards.service.render_short", render)
    monkeypatch.setattr("content_rewards.service.inspect_video", lambda path: video_metadata(path) | {"duration_seconds": 45.0})
    job = workflow.prepare_best("youtube")
    assert measured == [45.0]
    assert job["title"] == "Approved headline"
    assert job["caption"] == "Paid promotion\n#Approved\n@brand.account"
    assert job["state"] == "rendered" and job["approval"] is None


@pytest.mark.parametrize("failure", ["square", "duration", "render", "short_bytes"])
def test_prepare_defers_unfulfillable_offer_and_prepares_next_small_offer(workflow, tmp_path, monkeypatch, failure):
    high = campaign_record(tmp_path, id="high", rate_per_1000_views_usd=100,
                           remaining_budget_usd=10000)
    small = campaign_record(tmp_path, id="small", rate_per_1000_views_usd=0.01)
    for item in high["publication_spec"]["requirements"]:
        if failure == "square" and item["id"] == "aspect_ratio":
            item["value"] = "1:1"
        if failure in {"duration", "short_bytes"} and item["id"] == "duration":
            item.update(minimum=90.0 if failure == "duration" else 45.0)
            item.update(maximum=120.0 if failure == "duration" else 60.0)
    workflow.import_campaigns([small, high])
    if failure == "render":
        def render(source, output, **kwargs):
            from content_rewards.media import MediaError
            high_jobs = [job for job in workflow.store.list("job") if job["campaign_id"] == "high"]
            if any(Path(output).stem == job["id"] for job in high_jobs):
                raise MediaError("Undecodable approved source")
            Path(output).write_bytes(b"rendered-mp4")
        monkeypatch.setattr("content_rewards.service.render_short", render)
    result = workflow.prepare_best("youtube")
    assert result["campaign_id"] == "small"
    assert result["approval"] is None and result["remote_id"] is None
    assert len(workflow.store.list("campaign")) == 2
    with workflow.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE kind='preparation_deferred' AND entity_id='high'").fetchone()[0] == 1


async def test_scheduler_prepare_uses_platform_and_does_not_repeat_candidate(workflow, tmp_path):
    workflow.import_campaigns([campaign_record(tmp_path)])
    workflow.settings.live_publishing = False
    workflow.store.schedule("prepare-instagram", "prepare", 60, {"platform": "instagram"}, 1000)
    result = await workflow.tick(1000)
    assert result == [{"id": "prepare-instagram", "status": "completed"}]
    jobs = workflow.store.list("job")
    assert len(jobs) == 1
    assert jobs[0]["platform"] == "instagram"
    assert jobs[0]["state"] == "rendered"
    assert jobs[0]["approval"] is None
    assert await workflow.tick(1059) == []
    repeated = await workflow.tick(1060)
    assert repeated[0]["status"] == "blocked"
    assert len(workflow.store.list("job")) == 1
