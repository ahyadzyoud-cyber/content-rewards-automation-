"""Critical compliance gates on real workflow transitions, using isolated fakes."""
from datetime import UTC, datetime

import pytest
from compliance_fixtures import publication_evidence, video_metadata

from content_rewards.config import Settings
from content_rewards.readiness import preflight
from content_rewards.service import Blocked, Workflow


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    workflow = Workflow(Settings(database=tmp_path / "private.sqlite", media_root=tmp_path / "media",
                                 youtube_channel_id="verified-test-channel", live_publishing=True))
    source = tmp_path / "licensed-fixture.mp4"
    source.write_bytes(b"synthetic approved source")
    campaign = {
        "id": "compliance-fixture", "title": "Synthetic compliant brief", "source": "manual",
        "source_url": "https://example.com/synthetic-test-brief", "rate_per_1000_views_usd": 1,
        "remaining_budget_usd": 100, "eligible_countries": ["JO"], "eligibility_verified": True,
        "eligibility_evidence": "Synthetic test only", "allowed_platforms": ["youtube"],
        "allows_new_accounts": True, "requirements_verified": True, "rights_verified": True,
        "materials": [str(source)], "evidence_checked_at": datetime.now(UTC).isoformat(),
        **publication_evidence(platform="youtube"),
    }
    workflow.import_campaigns([campaign])

    def render(source, output, **kwargs):
        output.write_bytes(b"synthetic rendered video")

    monkeypatch.setattr("content_rewards.service.render_short", render)
    monkeypatch.setattr("content_rewards.service.inspect_video", video_metadata)
    job = workflow.plan(campaign["id"], "youtube", source, "Reviewed title", "Reviewed caption")
    workflow.render(job["id"])
    return workflow, workflow.store.get("job", job["id"])


def set_requirement(workflow, job, category, **updates):
    campaign = workflow.store.get("campaign", job["campaign_id"])
    requirement = next(item for item in campaign["publication_spec"]["requirements"] if item["category"] == category)
    requirement.update(updates)
    workflow.import_campaigns([campaign])


class NoWritePublisher:
    def __init__(self):
        self.calls = []

    async def verify_account(self):
        self.calls.append("identity")
        return {"id": "verified-test-channel"}

    async def upload(self, *args):
        self.calls.append("upload")
        pytest.fail("An unverified deliverable must not reach a provider write")


def test_legacy_record_remains_readable_but_cannot_be_approved(delivery):
    workflow, job = delivery
    campaign = workflow.store.get("campaign", job["campaign_id"])
    campaign.pop("publication_spec")
    workflow.import_campaigns([campaign])
    assert workflow.store.get("job", job["id"])["state"] == "rendered"
    with pytest.raises(Blocked, match="Full official brief"):
        workflow.approve(job["id"], "Owner review cannot replace a complete brief")
    assert workflow.store.get("job", job["id"])["approval"] is None


@pytest.mark.parametrize("state", ["unknown", "unmet"])
def test_critical_unknown_or_unmet_clause_blocks_owner_approval(delivery, state):
    workflow, job = delivery
    set_requirement(workflow, job, "livestream", status=state)
    with pytest.raises(Blocked, match="livestream"):
        workflow.approve(job["id"], "No waiver of mandatory campaign conditions")


@pytest.mark.parametrize("measurement", [
    {"duration_seconds": 61.0}, {"width": 1920, "height": 1080},
    {"container_brand": "qt"},
])
def test_actual_measured_duration_aspect_and_format_block_approval(delivery, monkeypatch, measurement):
    workflow, job = delivery
    monkeypatch.setattr("content_rewards.service.inspect_video", lambda path: video_metadata(path) | measurement)
    with pytest.raises(Blocked, match="Critical brief requirement"):
        workflow.approve(job["id"], "The actual media must meet the brief")


@pytest.mark.parametrize("category,check,values", [
    ("title", "title_contains", ["Required hook"]),
    ("caption", "caption_contains", ["Required disclosure"]),
    ("hashtags", "hashtags", ["#required_campaign"]),
    ("mentions", "mentions", ["@required_brand"]),
])
def test_missing_literal_metadata_requirements_block_approval(delivery, category, check, values):
    workflow, job = delivery
    set_requirement(workflow, job, category, status="verified", check=check, values=values)
    with pytest.raises(Blocked, match=category):
        workflow.approve(job["id"], "Required caption fragments cannot be assumed present")


def test_manual_proof_requires_exact_review_and_never_implicitly_approves(delivery):
    workflow, job = delivery
    set_requirement(workflow, job, "content", status="verified", check="manual")
    with pytest.raises(Blocked, match="content"):
        workflow.approve(job["id"], "Broad approval is not individual content evidence")
    reviewed = workflow.review_compliance(job["id"], {
        "content": {"status": "verified", "evidence_url": "https://example.com/private-content-review",
                    "note": "Synthetic fixture: reviewed the exact rendered subject and claims"},
    })
    assert reviewed["state"] == "rendered" and reviewed["approval"] is None
    approved = workflow.approve(job["id"], "Separate explicit owner publication approval")
    assert approved["state"] == "approved"
    revised = workflow.review_compliance(job["id"], {})
    assert revised["state"] == "rendered" and revised["approval"] is None


def test_changed_metadata_invalidates_manual_review_before_approval(delivery):
    workflow, job = delivery
    set_requirement(workflow, job, "rights", status="verified", check="manual")
    reviewed = workflow.review_compliance(job["id"], {
        "rights": {"status": "verified", "evidence_url": "https://example.com/fixture-license",
                   "note": "Synthetic fixture: exact output and intended account licensed"},
    })
    reviewed["caption"] = "A changed caption after review"
    workflow.store.put("job", job["id"], reviewed)
    with pytest.raises(Blocked, match="rights"):
        workflow.approve(job["id"], "The previous proof is bound to different metadata")


async def test_manual_proof_edit_invalidates_existing_owner_approval(delivery):
    workflow, job = delivery
    set_requirement(workflow, job, "content", status="verified", check="manual")
    workflow.review_compliance(job["id"], {
        "content": {"status": "verified", "evidence_url": "https://example.com/content-review",
                    "note": "Synthetic exact output content reviewed"},
    })
    approved = workflow.approve(job["id"], "Owner approves the exact evidence and deliverable")
    approved["compliance_review"]["proofs"]["content"]["note"] = "Changed evidence after approval"
    workflow.store.put("job", job["id"], approved)
    publisher = NoWritePublisher()
    with pytest.raises(Blocked, match="changed after approval"):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == []


@pytest.mark.parametrize("missing", ["publication_spec", "payout_evidence", "qualifying_views_terms"])
async def test_legacy_or_forged_approval_cannot_bypass_mandatory_publish_gate(delivery, missing):
    workflow, job = delivery
    campaign = workflow.store.get("campaign", job["campaign_id"])
    campaign[missing] = None if missing == "publication_spec" else ""
    workflow.import_campaigns([campaign])
    job.update(state="approved", approval={"digest": workflow._digest(job), "reason": "Old or manually injected approval"})
    workflow.store.put("job", job["id"], job)
    publisher = NoWritePublisher()
    with pytest.raises(Blocked):
        await workflow.publish(job["id"], publisher)
    assert publisher.calls == []


def test_minimum_views_and_submission_proofs_remain_pending_after_prepublication_pass(delivery):
    workflow, job = delivery
    set_requirement(workflow, job, "minimum_views", status="verified", stage="postpublication",
                    statement="Synthetic fixture needs 1,000 real views before submission")
    set_requirement(workflow, job, "submission", status="verified", stage="submission",
                    statement="Synthetic fixture needs the actual public URL and view proof")
    approved = workflow.approve(job["id"], "Approve publication only; no views or rewards claimed")
    report = workflow.publication_compliance(approved)
    assert report["compliant"]
    assert {item["category"] for item in report["pending_postpublication"]} == {"minimum_views", "submission"}
    assert all(item["status"] == "pending" for item in report["pending_postpublication"])
    assert workflow.store.list("submission") == []


def test_untrusted_feed_cannot_self_attest_full_brief_review(delivery):
    workflow, job = delivery
    campaign = workflow.store.get("campaign", job["campaign_id"])
    workflow.import_campaigns([campaign], untrusted_feed=True)
    assert workflow.store.get("campaign", campaign["id"])["publication_spec"] is None


def test_preflight_exposes_compliance_inventory_without_mutation(delivery, monkeypatch):
    workflow, job = delivery
    set_requirement(workflow, job, "livestream", status="unknown")
    monkeypatch.setattr("content_rewards.readiness.inspect_video", video_metadata)
    before = workflow.store.get("job", job["id"])
    report = preflight(workflow, job["id"])
    assert not report["compliance"]["compliant"]
    assert any("livestream" in reason for reason in report["blockers"])
    assert report["external_writes"] is False
    assert workflow.store.get("job", job["id"]) == before


@pytest.mark.parametrize("operation", ["review", "approve"])
def test_review_or_approval_cannot_overwrite_a_concurrent_publication_claim(delivery, monkeypatch, operation):
    workflow, job = delivery
    original = workflow.store.claim_job

    def claim_after_concurrent_change(key, expected, updated, previous=None):
        current = workflow.store.get("job", key)
        current["state"] = "publishing"
        workflow.store.put("job", key, current)
        return original(key, expected, updated, previous)

    monkeypatch.setattr(workflow.store, "claim_job", claim_after_concurrent_change)
    with pytest.raises(Blocked, match="changed during"):
        if operation == "review":
            workflow.review_compliance(job["id"], {})
        else:
            workflow.approve(job["id"], "Review must not reset a publication claim")
    assert workflow.store.get("job", job["id"])["state"] == "publishing"
