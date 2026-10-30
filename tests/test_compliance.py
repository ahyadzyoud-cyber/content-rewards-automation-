"""Actual publication criteria are separate from broad campaign review flags."""
import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from content_rewards.compliance import (
    CATEGORIES,
    JobComplianceReview,
    PublicationSpec,
    compliance_report,
)

NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
SOURCE = "https://example.com/campaign/official-brief"
BRIEF = "Temporary test brief, not a real opportunity."
DIGEST = "a" * 64
MEDIA = {"width": 1080, "height": 1920, "duration_seconds": 30.0,
         "container_format": "mov,mp4,m4a,3gp,3g2,mj2", "container_brand": "isom"}
JOB = {"platform": "youtube", "title": "Exact headline", "caption": "Paid promotion #Brand @brand.account"}


def requirement(category, **changes):
    return {"id": category, "category": category, "status": "not_applicable", "stage": "prepublication",
            "statement": "Test brief contains no additional requirement in this category",
            "evidence_url": SOURCE, "evidence_note": "Operator reviewed this entire test brief."} | changes


def spec(**changes):
    return {"full_brief_text": BRIEF, "brief_sha256": hashlib.sha256(BRIEF.encode()).hexdigest(),
            "official_source_url": SOURCE, "reviewed_at": NOW, "review_complete": True,
            "requirements": [requirement(category) for category in sorted(CATEGORIES)]} | changes


def report(*, req=None, media=MEDIA, job=JOB, specification=None, digest=DIGEST):
    value = deepcopy(specification if specification is not None else spec())
    if req:
        value["requirements"] = [item for item in value["requirements"] if item["id"] != req["id"]] + [req]
    return compliance_report({"publication_spec": value}, job, media, binding_digest=digest, now=NOW)


def mechanical(category, check, **parameters):
    return requirement(category, status="verified", check=check, **parameters)


def test_legacy_campaign_is_readable_but_cannot_pass_with_only_broad_flags():
    result = compliance_report({"requirements_verified": True, "rights_verified": True}, JOB, MEDIA,
                               binding_digest=DIGEST, now=NOW)
    assert result["compliant"] is False
    assert "Full official brief" in result["blockers"][0]


@pytest.mark.parametrize("changes", [{"review_complete": False}, {"reviewed_at": NOW - timedelta(days=8)},
                                     {"reviewed_at": NOW + timedelta(hours=1)}, {"requirements": []}])
def test_inventory_cannot_assume_missing_categories_or_undated_stale_review(changes):
    assert not report(specification=spec(**changes))["compliant"]


@pytest.mark.parametrize("changes", [{"status": "not_applicable", "evidence_note": ""},
                                     {"status": "verified", "evidence_url": None},
                                     {"status": "verified", "statement": "   "}])
def test_known_and_explicit_absence_require_source_and_meaningful_conclusion(changes):
    with pytest.raises(ValidationError):
        report(req=requirement("content", **changes))


@pytest.mark.parametrize("changes", [{"full_brief_text": "changed brief"}, {"review_complete": "true"},
                                     {"official_source_url": "https://example.com/brief?token=private"},
                                     {"reviewed_at": NOW.replace(tzinfo=None)}])
def test_complete_review_rejects_hash_changes_ambiguous_flags_and_unsafe_sources(changes):
    with pytest.raises(ValidationError):
        PublicationSpec.model_validate(spec(**changes))


def test_duplicate_requirement_ids_and_unknown_categories_are_not_silently_ignored():
    with pytest.raises(ValidationError, match="unique"):
        PublicationSpec.model_validate(spec(requirements=[requirement("content"), requirement("content")]))
    with pytest.raises(ValidationError, match="category"):
        PublicationSpec.model_validate(spec(requirements=[requirement("invented")]))


@pytest.mark.parametrize("req", [
    requirement("rights", status="verified", check="platform", value="youtube"),
    requirement("content", status="verified", check="caption_contains", values=["a caption is not video content"]),
    requirement("content", status="verified", check="duration", minimum=30.0),
])
def test_wrong_checker_cannot_bypass_a_mandatory_gate(req):
    with pytest.raises(ValidationError):
        report(req=req)


def test_optional_unknown_entries_cannot_satisfy_mandatory_category_coverage():
    specification = spec(requirements=[requirement(category, status="unknown", critical=False)
                                       for category in sorted(CATEGORIES)])
    result = report(specification=specification)
    assert not result["compliant"]
    assert any("Mandatory requirement categories" in blocker for blocker in result["blockers"])


@pytest.mark.parametrize("category", ["platform", "duration", "format", "aspect_ratio", "content", "rights", "livestream"])
def test_physical_and_human_requirements_cannot_be_deferred_past_publication(category):
    specification = spec()
    specification["requirements"] = [requirement(category, status="verified", stage="postpublication")
                                     if item["category"] == category else item for item in specification["requirements"]]
    result = report(specification=specification)
    assert not result["compliant"]
    assert any("before publication" in blocker for blocker in result["blockers"])


def test_verified_minimum_views_cannot_be_claimed_before_the_video_is_published():
    result = report(req=requirement("minimum_views", status="verified", stage="prepublication"))
    assert not result["compliant"]


@pytest.mark.parametrize("category", ["platform", "duration", "format", "aspect_ratio"])
def test_manual_attestation_cannot_replace_actual_measurement_of_technical_requirement(category):
    job = proof_job(proofs={category: {"status": "verified", "evidence_url": SOURCE,
                                      "note": "Claimed to have inspected without machine evidence"}})
    assert not report(req=requirement(category, status="verified"), job=job)["compliant"]


@pytest.mark.parametrize("state", ["unknown", "unmet"])
@pytest.mark.parametrize("stage", ["prepublication", "postpublication", "submission"])
def test_unknown_critical_interpretation_blocks_even_when_eventual_outcome_is_later(state, stage):
    result = report(req=requirement("minimum_views", status=state, stage=stage))
    assert not result["compliant"]
    assert any("minimum_views" in blocker for blocker in result["blockers"])


def test_known_postpublication_views_and_submission_proof_remain_pending_not_passed():
    specification = spec()
    specification["requirements"] = [
        requirement(item["category"], status="verified", stage="postpublication" if item["category"] == "minimum_views" else "submission")
        if item["category"] in {"minimum_views", "submission"} else item for item in specification["requirements"]]
    result = report(specification=specification)
    assert result["compliant"] and result["blockers"] == []
    assert {item["id"] for item in result["pending_postpublication"]} == {"minimum_views", "submission"}
    assert all(item["status"] == "pending" for item in result["pending_postpublication"])


@pytest.mark.parametrize("category,check,parameters,media,job,expected", [
    ("platform", "platform", {"value": "youtube"}, MEDIA, JOB, True),
    ("platform", "platform", {"value": "instagram"}, MEDIA, JOB, False),
    ("duration", "duration", {"minimum": 30.0, "maximum": 60.0}, MEDIA, JOB, True),
    ("duration", "duration", {"minimum": 31.0}, MEDIA, JOB, False),
    ("duration", "duration", {"maximum": 29.0}, MEDIA, JOB, False),
    ("duration", "duration", {}, MEDIA, JOB, False),
    ("duration", "duration", {"minimum": 1.0}, MEDIA | {"duration_seconds": True}, JOB, False),
    ("aspect_ratio", "aspect_ratio", {"value": "9:16"}, MEDIA, JOB, True),
    ("aspect_ratio", "aspect_ratio", {"value": "1:1"}, MEDIA, JOB, False),
    ("format", "format", {"value": "mp4"}, MEDIA, JOB, True),
    ("format", "format", {"value": "mp4"}, MEDIA | {"container_brand": "qt  "}, JOB, False),
    ("format", "format", {"value": "mov"}, MEDIA | {"container_brand": "qt  "}, JOB, True),
    ("format", "format", {"value": "mp4"}, MEDIA | {"container_brand": "unknown"}, JOB, False),
    ("format", "format", {"value": "webm"}, MEDIA, JOB, False),
    ("format", "format", {"value": "mp4"}, None, JOB, False),
    ("title", "title_contains", {"values": ["Exact headline"]}, MEDIA, JOB, True),
    ("caption", "caption_contains", {"values": ["Paid promotion"]}, MEDIA, JOB, True),
    ("caption", "caption_contains", {"values": ["Required claim"]}, MEDIA, JOB, False),
    ("hashtags", "hashtags", {"values": ["#brand"]}, MEDIA, JOB, True),
    ("hashtags", "hashtags", {"values": ["#brand"]}, MEDIA, JOB | {"caption": "#brand_fake"}, False),
    ("hashtags", "hashtags", {"values": ["#brand"]}, MEDIA, JOB | {"caption": "Disclosure #Brand."}, True),
    ("mentions", "mentions", {"values": ["@brand"]}, MEDIA, JOB, False),
    ("mentions", "mentions", {"values": ["@brand.account"]}, MEDIA, JOB, True),
    ("mentions", "mentions", {"values": ["@brand account"]}, MEDIA, JOB, False),
])
def test_actual_media_and_exact_metadata_must_meet_machine_requirements(category, check, parameters, media, job, expected):
    result = report(req=mechanical(category, check, **parameters), media=media, job=job)
    assert result["compliant"] is expected


def proof_job(**changes):
    review = {"digest": DIGEST, "reviewed_at": NOW,
              "proofs": {"content": {"status": "verified", "evidence_url": SOURCE,
                                     "note": "Operator viewed the exact rendered bytes and confirmed the required content."}}}
    return JOB | {"compliance_review": review | changes}


def test_manual_content_needs_individual_evidence_bound_to_exact_bytes_and_metadata():
    req = requirement("content", status="verified")
    assert not report(req=req)["compliant"]
    assert report(req=req, job=proof_job())["compliant"]
    assert not report(req=req, job=proof_job(), digest="b" * 64)["compliant"]
    assert not report(req=req, job=proof_job(reviewed_at=NOW - timedelta(days=8)))["compliant"]
    assert not report(req=req, job=proof_job(proofs={"content": {"status": "not_applicable", "evidence_url": SOURCE,
                                                               "note": "An actual mandatory clause cannot be waived."}}))["compliant"]


def test_proofs_cannot_satisfy_other_inventory_ids_or_use_credential_bearing_sources():
    job = proof_job(proofs={"not_in_brief": {"status": "verified", "evidence_url": SOURCE, "note": "Not applicable here"}})
    assert not report(job=job)["compliant"]
    with pytest.raises(ValidationError):
        JobComplianceReview.model_validate({"digest": DIGEST, "reviewed_at": NOW,
                                           "proofs": {"content": {"status": "verified", "evidence_url": "https://u:secret@example.com/",
                                                                  "note": "Unsafe credential-bearing source"}}})


def test_compliance_report_does_not_mutate_inputs_or_claim_reward_acceptance():
    specification, job, media = spec(), deepcopy(JOB), deepcopy(MEDIA)
    before = deepcopy((specification, job, media))
    result = report(specification=specification, job=job, media=media)
    assert (specification, job, media) == before
    assert result["compliant"]
    assert "approved" not in result and "reward" not in result
