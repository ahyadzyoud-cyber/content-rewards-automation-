"""Campaign workflow with durable write barriers around external publishing."""
import asyncio
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

from .compliance import JobComplianceReview, compliance_report
from .config import Settings
from .media import MediaError, inspect_video, render_short
from .models import Campaign
from .ranking import rank_campaigns
from .store import Store, utcnow


class Blocked(ValueError):
    """An operation needs verified evidence or explicit authorization."""


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Workflow:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.store = Store(self.settings.database)
        self._youtube_tokens = None

    def import_campaigns(self, records: list[dict], *, untrusted_feed: bool = False) -> int:
        # Validate the entire batch before writing anything.
        campaigns = [Campaign.model_validate(record) for record in records]
        if len({c.id for c in campaigns}) != len(campaigns):
            raise ValueError("Duplicate campaign IDs in import")
        for campaign in campaigns:
            if untrusted_feed:
                campaign.eligibility_verified = False
                campaign.requirements_verified = False
                campaign.rights_verified = False
                campaign.payout_eligibility_verified = False
                campaign.automation_authorized = False
                campaign.evidence_checked_at = None
                # A provider feed cannot attest that its own complete brief or
                # manual requirements were independently reviewed by the owner.
                campaign.publication_spec = None
            self.store.put("campaign", campaign.id, campaign.model_dump(mode="json"))
        self.store.event("campaign_import", "batch", {"count": len(campaigns), "untrusted_feed": untrusted_feed})
        return len(campaigns)

    def rank(self, platform: str | None = None) -> list[dict]:
        return [s.model_dump() for s in rank_campaigns(
            [Campaign.model_validate(c) for c in self.store.list("campaign")],
            platforms=[platform] if platform else ["youtube", "instagram"],
        )]

    def campaign_for(self, campaign_id: str, platform: str) -> Campaign:
        campaign = Campaign.model_validate(self.store.get("campaign", campaign_id))
        score = rank_campaigns([campaign], platforms=[platform])[0]
        if not score.selectable:
            raise Blocked("; ".join(score.blockers))
        return campaign

    def plan(self, campaign_id: str, platform: str, source: Path, title: str, caption: str = "", *, _automatic: bool = False) -> dict:
        campaign = self.campaign_for(campaign_id, platform)
        source = Path(source).resolve(strict=True)
        approved = [Path(p).resolve() for p in campaign.materials if "://" not in p]
        if source not in approved or not source.is_file():
            raise Blocked("Use an explicitly approved local material listed in this campaign")
        if not title.strip() or len(title) > 100 or len(caption) > 2200:
            raise ValueError("Title must be 1..100 characters; caption at most 2200")
        job = {"id": uuid4().hex, "campaign_id": campaign_id, "platform": platform,
               "source_path": str(source), "source_sha256": file_hash(source),
               "title": title, "caption": caption, "state": "planned", "created_at": utcnow(),
               "media_path": None, "remote_id": None, "container_id": None, "video_url": None,
               "approval": None, "error": None}
        if _automatic:
            if not self.store.create_candidate(job):
                raise Blocked("Another worker already prepared this campaign/platform")
        else:
            self.store.put("job", job["id"], job)
        return job

    def render(self, job_id: str, duration: float = 30) -> dict:
        job = self.store.get("job", job_id)
        if job["state"] != "planned":
            raise Blocked("Only a planned job can be rendered")
        campaign = self.campaign_for(job["campaign_id"], job["platform"])
        self._check_material(job, campaign)
        if file_hash(Path(job["source_path"])) != job["source_sha256"]:
            raise Blocked("Approved source changed; create a new plan")
        self.settings.media_root.mkdir(parents=True, exist_ok=True)
        output = self.settings.media_root.resolve() / (job_id + ".mp4")
        render_short(Path(job["source_path"]), output, rights_verified=campaign.rights_verified,
                     duration_seconds=duration, caption=job["title"])
        job.update(state="rendered", media_path=str(output), media_sha256=file_hash(output))
        self.store.put("job", job_id, job)
        self.store.event("rendered", job_id, {"sha256": job["media_sha256"]})
        return job

    def prepare_best(self, platform: str) -> dict:
        """Automatically select and render an eligible candidate for human publication review."""
        candidates = [score for score in self.rank(platform) if score["selectable"]]
        if not candidates:
            raise Blocked("No verified eligible campaign is available for this platform")
        for score in candidates:
            campaign = self.campaign_for(score["campaign_id"], platform)
            # One candidate per campaign/account; an uncertain attempt must never create a new duplicate.
            existing = [job for job in self.store.list("job") if job["campaign_id"] == campaign.id
                        and job["platform"] == platform]
            if existing:
                continue
            sources = [Path(p) for p in campaign.materials if "://" not in p and Path(p).is_file()]
            if not sources:
                continue
            try:
                duration, title, caption = self._preparation_settings(campaign)
                job = self.plan(campaign.id, platform, sources[0], title, caption, _automatic=True)
                draft = self.render(job["id"], duration)
                report = self.publication_compliance(draft)
                machine_checks = {item.id for item in campaign.publication_spec.requirements
                                  if item.critical and item.stage == "prepublication"
                                  and item.status == "verified" and item.check != "manual"} if campaign.publication_spec else set()
                if any(check["id"] in machine_checks and check["status"] != "verified"
                       for check in report["checks"]):
                    raise Blocked("Rendered bytes or metadata do not meet the required campaign constraints")
                return draft
            except (Blocked, MediaError) as error:
                # A failed preparation is not a failed publication. Retain its
                # record and reservation; never reset an uncertain write barrier.
                self.store.event("preparation_deferred", campaign.id, {"error_type": type(error).__name__})
                continue
        raise Blocked("Eligible campaigns already have candidates, need approved media, or have unsupported preparation requirements")

    @staticmethod
    def _preparation_settings(campaign: Campaign) -> tuple[float, str, str]:
        """Apply reviewed mechanical constraints supported by the existing editor.

        Subjective content and human-participation proof still need review of
        the rendered bytes. This does not establish publication compliance.
        """
        lower, upper = 0.0, 60.0
        title_parts, caption_parts = [], []
        for item in campaign.publication_spec.requirements if campaign.publication_spec else []:
            if item.stage != "prepublication" or item.status != "verified":
                continue
            if item.check == "duration":
                lower = max(lower, item.minimum or 0.0)
                upper = min(upper, item.maximum if item.maximum is not None else 60.0)
            elif item.check == "format" and item.value != "mp4":
                raise Blocked("The existing editor cannot produce the campaign's required container")
            elif item.check == "aspect_ratio":
                try:
                    width, height = (int(value) for value in (item.value or "").split(":"))
                    if width <= 0 or height <= 0 or width * 16 != height * 9:
                        raise ValueError
                except ValueError:
                    raise Blocked("The existing editor cannot produce the campaign's required aspect ratio") from None
            elif item.check == "title_contains":
                title_parts.extend(item.values or [])
            elif item.check in {"caption_contains", "hashtags", "mentions"}:
                caption_parts.extend(item.values or [])
        if lower > upper or upper <= 0:
            raise Blocked("The required duration cannot be produced by the existing editor")
        title = " ".join(dict.fromkeys(title_parts)) if title_parts else campaign.title[:100]
        caption = "\n".join(dict.fromkeys(caption_parts))
        if not title.strip() or len(title) > 100 or len(caption) > 2200:
            raise Blocked("Required metadata exceeds the configured publication adapter's limits")
        return max(lower, min(30.0, upper)), title, caption

    def _check_material(self, job: dict, campaign: Campaign):
        approved = [Path(p).resolve() for p in campaign.materials if "://" not in p]
        if Path(job["source_path"]).resolve() not in approved:
            raise Blocked("Source material authorization was revoked; create a new plan")

    def _digest(self, job: dict, media_hash: str | None = None, *, include_review: bool = True) -> str:
        # Approval is bound to exact media, metadata, target and current campaign evidence.
        fields = {k: job.get(k) for k in ("id", "campaign_id", "platform", "title", "caption", "video_url")}
        fields["sha256"] = media_hash or file_hash(Path(job["media_path"]))
        fields["campaign"] = self.store.get("campaign", job["campaign_id"])
        fields["account"] = (self.settings.youtube_channel_id if job["platform"] == "youtube"
                             else self.settings.instagram_account_id)
        if include_review:
            fields["compliance_review"] = job.get("compliance_review")
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    def publication_compliance(self, job: dict, *, media_path: Path | None = None,
                               media: dict | None = None) -> dict:
        """Check the exact deliverable without approval, network I/O or writes."""
        campaign = Campaign.model_validate(self.store.get("campaign", job["campaign_id"]))
        blockers = []
        measured = media
        binding = ""
        try:
            if not job.get("media_path"):
                raise Blocked("Render this job before publication review")
            path = media_path or Path(job["media_path"])
            actual_hash = file_hash(path)
            if actual_hash != job.get("media_sha256"):
                blockers.append("Rendered media differs from the prepared job")
            measured = measured if measured is not None else inspect_video(path)
            binding = self._digest(job, actual_hash, include_review=False)
        except (Blocked, ValueError, OSError):
            blockers.append("Rendered media is missing, invalid or not ready for review")
        report = compliance_report(campaign, job, measured, binding_digest=binding)
        blockers += report["blockers"]
        if not campaign.payout_eligibility_verified or not campaign.payout_evidence.strip():
            blockers.append("Verify Jordan payout support and completion of this provider's payout setup")
        if not campaign.qualifying_views_terms.strip():
            blockers.append("Verify qualifying-view rules, measurement window and submission requirements")
        no_deadline_reviewed = bool(campaign.publication_spec and any(
            item.category == "deadline" and item.status == "not_applicable"
            for item in campaign.publication_spec.requirements))
        if campaign.expires_at is None and not no_deadline_reviewed:
            blockers.append("Verify the current campaign deadline or explicitly documented absence of a deadline")
        return report | {"blockers": blockers, "compliant": not blockers, "media": measured}

    def _require_publication_compliance(self, job: dict, *, media_path: Path | None = None):
        report = self.publication_compliance(job, media_path=media_path)
        if report["blockers"]:
            raise Blocked("; ".join(report["blockers"]))

    def review_compliance(self, job_id: str, proofs: dict, *, video_url: str | None = None) -> dict:
        """Record individual manual reviews, bound to bytes, metadata and target.

        This is separate from publication approval. Recording or changing a
        review invalidates any previous publication approval.
        """
        job = self.store.get("job", job_id)
        if job["state"] not in {"rendered", "approved"}:
            raise Blocked("Only a rendered deliverable can receive a compliance review")
        previous = dict(job)
        self.campaign_for(job["campaign_id"], job["platform"])
        if video_url is not None:
            job["video_url"] = video_url
            self._check_instagram_url(job)
        if file_hash(Path(job["media_path"])) != job.get("media_sha256"):
            raise Blocked("Rendered file changed; review a newly rendered deliverable")
        review = JobComplianceReview(digest=self._digest(job, include_review=False),
                                     reviewed_at=utcnow(), proofs=proofs)
        job["compliance_review"] = review.model_dump(mode="json")
        job.update(state="rendered", approval=None)
        if not self.store.claim_job(job_id, previous["state"], job, previous):
            raise Blocked("The deliverable changed during compliance review; review the current state again")
        self.store.event("compliance_reviewed", job_id, {"at": review.reviewed_at.isoformat()})
        return job

    def approve(self, job_id: str, reason: str, *, video_url: str | None = None) -> dict:
        job = self.store.get("job", job_id)
        if job["state"] != "rendered":
            raise Blocked("Only a rendered job can be approved; review the actual output first")
        previous = dict(job)
        self.campaign_for(job["campaign_id"], job["platform"])
        account = (self.settings.youtube_channel_id if job["platform"] == "youtube"
                   else self.settings.instagram_account_id)
        if not account or not reason.strip():
            raise Blocked("An explicit target account and a review reason are required")
        if video_url:
            parsed = httpx.URL(video_url)
            if parsed.scheme != "https" or not parsed.host or parsed.userinfo or parsed.query:
                raise ValueError("Use a public HTTPS media URL without credentials or signed query secrets")
            job["video_url"] = video_url
        if job["platform"] == "instagram" and not job["video_url"]:
            raise Blocked("Instagram requires a public HTTPS URL serving these exact approved video bytes")
        if job["platform"] == "instagram":
            self._check_instagram_url(job)
        if file_hash(Path(job["media_path"])) != job["media_sha256"]:
            raise Blocked("Rendered file changed; create and review a new job")
        self._require_publication_compliance(job)
        job["approval"] = {"digest": self._digest(job), "at": utcnow(), "reason": reason}
        job["state"] = "approved"
        if not self.store.claim_job(job_id, "rendered", job, previous):
            raise Blocked("The deliverable changed during approval; review the current state again")
        self.store.event("publication_approved", job_id, {"at": job["approval"]["at"]})
        return job

    def _check_instagram_url(self, job: dict):
        from urllib.parse import urlsplit
        parsed = urlsplit(job["video_url"] or "")
        host = self.settings.instagram_media_host
        if (not host or parsed.scheme != "https" or parsed.hostname != host or parsed.query
                or parsed.username or parsed.password or parsed.port not in {None, 443}
                or Path(parsed.path).name != job["media_sha256"] + ".mp4"):
            raise Blocked("Instagram hosting requires a verified immutable HTTPS media host and a SHA256-named MP4 matching this job")

    async def _verify_instagram_media(self, job: dict):
        from .feeds import validate_feed_url
        self._check_instagram_url(job)
        validate_feed_url(job["video_url"], self.settings.instagram_media_host)
        digest = hashlib.sha256()
        size = 0
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            async with client.stream("GET", job["video_url"]) as response:
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0] != "video/mp4":
                    raise Blocked("Instagram media host must serve video/mp4")
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 200 * 1024 * 1024:
                        raise Blocked("Hosted video exceeds 200MiB validation limit")
                    digest.update(chunk)
        if digest.hexdigest() != job["media_sha256"]:
            raise Blocked("Hosted Instagram media differs from the approved video")

    async def _publisher(self, platform: str):
        from .integrations import InstagramPublisher, YouTubePublisher
        if platform == "youtube":
            if not self.settings.credential_status()["youtube"]:
                raise Blocked("Authorize YouTube and configure its verified channel ID in environment settings")
            from .oauth import StaticTokenProvider, YouTubeTokenProvider
            if self._youtube_tokens is None:
                if self.settings.youtube_refresh_configured():
                    self._youtube_tokens = YouTubeTokenProvider(self.settings.google_client_id,
                                                               self.settings.google_client_secret,
                                                               self.settings.youtube_refresh_token)
                else:
                    self._youtube_tokens = StaticTokenProvider(self.settings.youtube_token)
            token = await self._youtube_tokens.get_access_token()
            return YouTubePublisher(token, privacy_status="public", token_provider=self._youtube_tokens)
        if not all((self.settings.instagram_token, self.settings.instagram_account_id, self.settings.instagram_api_version)):
            raise Blocked("Authorize an eligible Instagram professional account and configure API version")
        return InstagramPublisher(self.settings.instagram_token, self.settings.instagram_account_id,
                                  self.settings.instagram_api_version)

    async def publish(self, job_id: str, publisher=None) -> dict:
        job = self.store.get("job", job_id)
        if not self.settings.live_publishing:
            raise Blocked("Live publishing is disabled; enable only after account authorization and publication review")
        if job["state"] != "approved" or not job["approval"]:
            raise Blocked("Publication requires approval of this exact job")
        self.campaign_for(job["campaign_id"], job["platform"])
        if self._digest(job) != job["approval"]["digest"]:
            raise Blocked("Media, metadata, evidence or target account changed after approval")
        self._require_publication_compliance(job)
        publisher = publisher or await self._publisher(job["platform"])
        expected = (self.settings.youtube_channel_id if job["platform"] == "youtube"
                    else self.settings.instagram_account_id)
        account = await publisher.verify_account()
        if account.get("id") != expected:
            raise Blocked("Authorized account does not match the approved publication target")
        if job["platform"] == "instagram":
            await self._verify_instagram_media(job)
            await publisher.require_publishing_capacity()
        # Verify after every network await and freeze the bytes that will actually be uploaded.
        campaign = self.campaign_for(job["campaign_id"], job["platform"])
        self._check_material(job, campaign)
        self.settings.media_root.mkdir(parents=True, exist_ok=True)
        staged = tempfile.NamedTemporaryFile(dir=self.settings.media_root, suffix=".mp4", delete=False)
        staged_path = Path(staged.name)
        try:
            with staged, Path(job["media_path"]).open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    staged.write(chunk)
                staged.flush()
                os.fsync(staged.fileno())
            if self._digest(job, file_hash(staged_path)) != job["approval"]["digest"]:
                raise Blocked("Media, evidence or account changed during verification; review again")
            self._require_publication_compliance(job, media_path=staged_path)
            return await self._publish_claimed(job, publisher, staged_path)
        finally:
            staged_path.unlink(missing_ok=True)

    async def _publish_claimed(self, job: dict, publisher, staged_path: Path) -> dict:
        job_id = job["id"]
        previous = dict(job)
        # Claim before the first external write. A crash leaves a durable barrier that cannot auto retry.
        job["state"] = "publishing"
        if not self.store.claim_job(job_id, "approved", job, previous):
            raise Blocked("Another worker already claimed this publication")
        try:
            if job["platform"] == "youtube":
                job["remote_id"] = await publisher.upload(staged_path, job["title"], job["caption"])
            else:
                job["container_id"] = await publisher.create_container(job["video_url"], job["caption"])
                self.store.put("job", job_id, job)
                for _ in range(30):
                    status = await publisher.container_status(job["container_id"])
                    if status == "FINISHED":
                        break
                    if status in {"ERROR", "EXPIRED"}:
                        raise Blocked("Instagram container failed; reconcile before another attempt")
                    await asyncio.sleep(10)
                else:
                    raise Blocked("Instagram container timed out; reconcile its status before retrying")
                # Other permitted apps can consume account quota during processing.
                await publisher.require_publishing_capacity()
                campaign = self.campaign_for(job["campaign_id"], job["platform"])
                self._check_material(job, campaign)
                if (self._digest(job, file_hash(staged_path)) != job["approval"]["digest"]
                        or self.store.get("job", job_id) != job):
                    raise Blocked("Approval or eligibility changed during Instagram processing; publication stopped")
                self._require_publication_compliance(job, media_path=staged_path)
                job["remote_id"] = await publisher.publish_container(job["container_id"])
            job["state"] = "published"
            job["published_at"] = utcnow()
            self.store.put("job", job_id, job)
            self.store.event("published", job_id, {"remote_id": job["remote_id"]})
        except Exception:
            job.update(state="needs_reconciliation", error="External publication outcome uncertain; inspect provider before retry")
            self.store.put("job", job_id, job)
            self.store.event("publication_uncertain", job_id, {})
            raise Blocked(job["error"]) from None
        return job

    async def collect_metrics(self, job_id: str, publisher=None) -> dict:
        job = self.store.get("job", job_id)
        if job["state"] != "published" or not job["remote_id"]:
            raise Blocked("Metrics require a confirmed published media ID")
        publisher = publisher or await self._publisher(job["platform"])
        metrics = await publisher.metrics(job["remote_id"])
        record = {"job_id": job_id, "at": utcnow(), "provider_metrics": metrics}
        self.store.put("metrics", job_id, record)
        self.store.event("metrics_snapshot", job_id, record)
        return record

    def record_submission(self, job_id: str, status: str, evidence_url: str, earnings_usd: float = 0) -> dict:
        import math
        if status not in {"prepared", "submitted", "approved", "rejected", "paid"}:
            raise ValueError("Invalid campaign submission status")
        if not math.isfinite(earnings_usd) or earnings_usd < 0:
            raise ValueError("Earnings must be finite and nonnegative")
        if earnings_usd > 0 and status not in {"approved", "paid"}:
            raise Blocked("Only verified approved or paid earnings may be recorded")
        job = self.store.get("job", job_id)
        if job["state"] != "published":
            raise Blocked("A submission requires a published job")
        parsed = httpx.URL(evidence_url)
        if parsed.scheme != "https" or not parsed.host or parsed.userinfo:
            raise ValueError("Submission evidence must be an HTTPS URL without credentials")
        record = {"job_id": job_id, "status": status, "evidence_url": evidence_url,
                  "earnings_usd": earnings_usd, "at": utcnow(), "verification": "operator_recorded"}
        self.store.put("submission", job_id, record)
        self.store.event("submission_recorded", job_id, record)
        return record

    async def discover(self) -> dict:
        from .feeds import fetch_campaigns
        feeds = self.store.list("feed")
        if not feeds:
            raise Blocked("No verified no-cost campaign feed configured; import a campaign export until provider API access is verified")
        results = []
        for feed in feeds:
            records = await fetch_campaigns(feed["url"], feed["allowed_host"])
            count = self.import_campaigns(records, untrusted_feed=True)
            results.append({"feed_id": feed["id"], "imported": count})
        return {"feeds": results}

    async def discover_whop(self, country: str = "JO", goal: str = "clipping", max_pages: int = 5) -> dict:
        """Read official creator-visible fixed rewards without importing them as CPM work."""
        from .whop import WhopBounties
        if not (self.settings.whop_token or (self.settings.whop_broker_url and self.settings.whop_broker_token)):
            raise Blocked("Authorize Whop through the owner cloud PKCE flow requesting only bounty:basic:read; manual WHOP_ACCESS_TOKEN remains optional")
        report = await WhopBounties(self.settings.whop_token, broker_url=self.settings.whop_broker_url,
                                  broker_token=self.settings.whop_broker_token).list_open_bounties(
            country=country, business_goal_type=goal, max_pages=max_pages,
        )
        self.store.put("whop_discovery", country.upper() + ":" + goal, report)
        self.store.event("whop_official_read", country.upper() + ":" + goal,
                         {"count": len(report["observations"]), "complete": report["pagination_complete"]})
        from .whop_ranking import BountyVerification, rank_whop_bounties
        verifications = {item["bounty_id"]: BountyVerification.model_validate(item)
                         for item in self.store.list("whop_verification")}
        # Raw account-visible responses stay in the private local ledger, never in
        # logs, public cloud checkpoints, CPM rankings, or approval records.
        return {"provider": "whop", "pricing_model": report["pricing_model"],
                "observed_at": report["observed_at"], "country_filter": report["country_filter"],
                "business_goal_type": goal, "pagination_complete": report["pagination_complete"],
                "rankings": rank_whop_bounties(report, verifications=verifications, country=country),
                "opportunities": [{key: item[key] for key in (
                    "id", "title", "currency", "gross_reward_amount", "spots_remaining",
                    "provider_reports_country_match", "new_account_eligibility_verified",
                )} for item in report["observations"]],
                "eligible_campaigns_verified": False, "live_publication_performed": False}

    async def tick(self, now: float | None = None) -> list[dict]:
        results = []
        # Claim just before execution; queued tasks never sit with an expiring lease.
        for _ in range(100):
            due = self.store.claim_due(time.time() if now is None else now, limit=1)
            if not due:
                break
            schedule = due[0]
            try:
                # Bound async I/O below the 30-minute lease. A cancelled publication
                # retains its durable publishing state for operator reconciliation.
                async with asyncio.timeout(900):
                    payload = json.loads(schedule["payload"])
                    action = schedule["action"]
                    if action == "rank":
                        result = self.rank(payload.get("platform"))
                        self.store.put("report", schedule["id"], {"at": utcnow(), "ranking": result})
                    elif action == "discover":
                        await self.discover()
                    elif action == "metrics":
                        await self.collect_metrics(payload["job_id"])
                    elif action == "prepare":
                        await asyncio.to_thread(self.prepare_best, payload["platform"])
                    else:
                        await self.publish(payload["job_id"])
                results.append({"id": schedule["id"], "status": "completed"})
            except Exception as exc:
                # Exception contents may include upstream URLs/credentials; persist type only.
                results.append({"id": schedule["id"], "status": "blocked" if isinstance(exc, Blocked) else "failed",
                                "error_type": type(exc).__name__})
            finally:
                self.store.finish_schedule(schedule["id"], schedule["lease_token"], time.time() if now is None else now)
        for result in results:
            self.store.event("schedule_run", result["id"], result)
        return results
