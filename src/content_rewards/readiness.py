"""Evidence reports; configuration presence is never presented as production proof."""
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .integrations import IntegrationError
from .media import inspect_video
from .service import Blocked, Workflow, file_hash


def readiness(workflow: Workflow) -> dict:
    store, config = workflow.store, workflow.settings
    campaigns = store.list("campaign")
    jobs = store.list("job")
    accounts = {item["platform"]: item for item in store.list("account_check")}
    required = []
    selections = {}
    for platform in ("youtube", "instagram"):
        rankings = workflow.rank(platform)
        candidates = [row for row in rankings if row["selectable"]]
        selections[platform] = {"eligible_candidates": len(candidates), "best": candidates[0] if candidates else None}
        if not candidates:
            required.append({"code": "campaign_access_" + platform,
                             "action": "Verify permitted provider campaign access, Jordan creator/payout eligibility, new-account terms and approved materials"})
        checked = accounts.get(platform, {})
        at = checked.get("checked_at")
        fresh = False
        if at:
            try:
                age = (datetime.now(UTC) - datetime.fromisoformat(at)).total_seconds()
                fresh = 0 <= age < 86400
            except (TypeError, ValueError):
                pass
        # Check proof against the current configured target. No IDs/tokens in this report.
        current_id = config.youtube_channel_id if platform == "youtube" else config.instagram_account_id
        authorized = bool(current_id and checked.get("status") == "verified" and fresh
                          and checked.get("account_id") == current_id)
        accounts[platform] = {"configured": config.credential_status()[platform], "identity_read_verified": authorized}
        if not authorized:
            required.append({"code": "authorize_" + platform,
                             "action": "Authorize the account in secure settings, then run verify-accounts"})
    if not config.youtube_refresh_configured():
        required.append({"code": "youtube_renewal", "action": "Authorize offline Google OAuth access for unattended YouTube credential renewal"})
    required.append({"code": "instagram_renewal", "action": "Verify supported Instagram token renewal and live API contract before unattended publishing"})
    if not config.instagram_media_host:
        required.append({"code": "instagram_hosting", "action": "Authorize an existing no-cost immutable HTTPS media host for Instagram"})
    published = [job for job in jobs if job["state"] == "published"]
    metrics = store.list("metrics")
    observed_metrics = {item["job_id"] for item in metrics}
    tracked = [job for job in published if job["id"] in observed_metrics]
    if not published:
        required.append({"code": "first_publication", "action": "Review and approve the first real rendered campaign video after account and campaign verification"})
    if not tracked:
        required.append({"code": "tracking", "action": "Verify real provider views and campaign submission/earnings tracking after authorized publication"})
    # A local process, a dry-run workflow, or user-set flag is not production evidence.
    required.append({"code": "production_execution", "action": "Verify free execution entitlement and a successful durable cloud production run"})
    return {"business_live": False, "as_of": datetime.now(UTC).isoformat(),
            "development": {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
                            "database": "available", "registered_schedules": len(store.schedules())},
            "campaigns": {"observed": len(campaigns), "selections": selections,
                          "official_live_discovery_verified": False},
            "accounts": accounts,
            "publication": {"live_mode_configured": config.live_publishing,
                            "confirmed_jobs": len(published), "jobs_with_metrics": len(tracked)},
            "required_actions": required}


async def verify_accounts(workflow: Workflow) -> dict:
    results = {}
    for platform in ("youtube", "instagram"):
        try:
            publisher = await workflow._publisher(platform)
            account = await publisher.verify_account()
            expected = (workflow.settings.youtube_channel_id if platform == "youtube"
                        else workflow.settings.instagram_account_id)
            if account.get("id") != expected:
                raise Blocked("Account identity does not match configured publication target")
            record = {"platform": platform, "status": "verified", "account_id": expected,
                      "checked_at": datetime.now(UTC).isoformat(), "operation": "read_only_identity"}
            workflow.store.put("account_check", platform, record)
            results[platform] = {"status": "verified", "operation": "read_only_identity"}
        except (Blocked, IntegrationError, ValueError):
            # Never keep a previous success after a failed current authorization check.
            workflow.store.put("account_check", platform,
                               {"platform": platform, "status": "blocked", "checked_at": datetime.now(UTC).isoformat()})
            results[platform] = {"status": "blocked", "action": "Check secure account configuration and API authorization"}
    return results


def preflight(workflow: Workflow, job_id: str) -> dict:
    """Produce a real job review packet without approving it or writing to providers."""
    job = workflow.store.get("job", job_id)
    blockers = []
    campaign = workflow.store.get("campaign", job["campaign_id"])
    ranking = next(row for row in workflow.rank(job["platform"]) if row["campaign_id"] == campaign["id"])
    blockers += ranking["blockers"]
    media = None
    try:
        if not job.get("media_path"):
            raise Blocked("Render this job before publication review")
        media = inspect_video(Path(job["media_path"]))
        if file_hash(Path(job["media_path"])) != job["media_sha256"]:
            blockers.append("Rendered media differs from the prepared job")
    except (Blocked, ValueError, OSError):
        blockers.append("Rendered media is missing, invalid or not ready for review")
    if job["platform"] == "instagram":
        try:
            workflow._check_instagram_url(job)
        except (Blocked, ValueError):
            blockers.append("Instagram immutable media hosting is not configured for this exact video")
    if not workflow.settings.credential_status()[job["platform"]]:
        blockers.append("Target account requires secure authorization")
    if not readiness(workflow)["accounts"][job["platform"]]["identity_read_verified"]:
        blockers.append("Verify the target account with a fresh matching read-only API identity check")
    if not job.get("approval"):
        blockers.append("Owner publication approval is pending")
    elif media is not None and workflow._digest(job) != job["approval"].get("digest"):
        blockers.append("Publication approval changed or is no longer valid; review the exact job again")
    if not campaign.get("payout_eligibility_verified") or not campaign.get("payout_evidence", "").strip():
        blockers.append("Verify Jordan payout support and completion of this provider's payout setup")
    if not campaign.get("qualifying_views_terms", "").strip():
        blockers.append("Verify qualifying-view rules, measurement window and submission requirements")
    if not campaign.get("expires_at"):
        blockers.append("Verify the current campaign deadline or explicitly documented absence of a deadline")
    return {"job_id": job_id, "campaign_source_url": campaign["source_url"],
            "campaign_id": campaign["id"], "campaign_title": campaign["title"],
            "platform": job["platform"], "title": job["title"], "caption": job["caption"],
            "score": ranking["score"], "media": media, "media_sha256": job.get("media_sha256"),
            "expires_at": campaign.get("expires_at"),
            "qualifying_views_terms": campaign.get("qualifying_views_terms", ""),
            "maximum_reward_per_video_usd": campaign.get("maximum_reward_per_video_usd"),
            "audience_country_requirements": campaign.get("audience_country_requirements", []),
            "requirements_to_review": campaign.get("requirements", []), "blockers": blockers,
            "external_writes": False, "approved_by_this_check": False,
            "campaign_submission_verified": False, "payout_verified": False,
            "payout_operator_attested": bool(campaign.get("payout_eligibility_verified") and campaign.get("payout_evidence"))}


def write_readiness(workflow: Workflow, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(readiness(workflow), indent=2) + "\n")
