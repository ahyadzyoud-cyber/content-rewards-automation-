"""Explicit synthetic publication evidence for isolated tests, never real campaigns."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from content_rewards.compliance import CATEGORIES


def publication_evidence(*, platform=None):
    """A fully reviewed artificial brief with no subjective deliverable claims."""
    brief = (
        "SYNTHETIC TEST BRIEF ONLY. Use the fixture's approved source. "
        "Either configured YouTube or Instagram target is allowed unless the "
        "platform check below restricts it. Produce an MP4, 9:16, 1–60 seconds. "
        "No other mandatory content, metadata, account, livestream, submission "
        "or disclosure conditions apply to this isolated fixture. Campaign "
        "envelope evidence supplies expiry, payout and qualifying-view terms."
    )
    source = "https://example.com/synthetic-test-brief"
    requirements = []
    for category in sorted(CATEGORIES):
        requirement = {
            "id": category, "category": category,
            "status": "not_applicable", "statement": "Synthetic brief has no additional " + category + " condition",
            "evidence_url": source, "evidence_note": "Reviewed the complete artificial test brief; no real-world attestation",
        }
        if category == "platform" and platform is not None:
            requirement.update(status="verified", statement="Use the fixture's exact target platform",
                               check="platform", value=platform)
        elif category == "duration":
            requirement.update(status="verified", statement="Use 1–60 seconds", check="duration", minimum=1.0, maximum=60.0)
        elif category == "format":
            requirement.update(status="verified", statement="Use MP4", check="format", value="mp4")
        elif category == "aspect_ratio":
            requirement.update(status="verified", statement="Use portrait 9:16", check="aspect_ratio", value="9:16")
        requirements.append(requirement)
    return {
        "publication_spec": {
            "full_brief_text": brief, "brief_sha256": sha256(brief.encode()).hexdigest(),
            "official_source_url": source, "reviewed_at": datetime.now(UTC).isoformat(),
            "review_complete": True, "requirements": requirements,
        },
        "payout_eligibility_verified": True,
        "payout_evidence": "Synthetic test owner payout verification only",
        "qualifying_views_terms": "Synthetic test qualifying views; no real reward or guarantee",
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }


def video_metadata(path):
    """Known fixture-byte metadata used only where rendering itself is mocked."""
    return {"path": str(path), "width": 1080, "height": 1920, "duration_seconds": 30.0,
            "container_format": "mov,mp4,m4a,3gp,3g2,mj2", "container_brand": "isom",
            "video_codec": "h264", "audio_codec": "aac",
            "pixel_format": "yuv420p", "frame_rate": "30/1"}
