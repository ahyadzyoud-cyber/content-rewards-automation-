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

from .config import Settings
from .media import render_short
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
            job = self.plan(campaign.id, platform, sources[0], campaign.title[:100], _automatic=True)
            return self.render(job["id"])
        raise Blocked("Eligible campaigns already have candidates or need approved local media")

    def _check_material(self, job: dict, campaign: Campaign):
        approved = [Path(p).resolve() for p in campaign.materials if "://" not in p]
        if Path(job["source_path"]).resolve() not in approved:
            raise Blocked("Source material authorization was revoked; create a new plan")

    def _digest(self, job: dict, media_hash: str | None = None) -> str:
        # Approval is bound to exact media, metadata, target and current campaign evidence.
        fields = {k: job.get(k) for k in ("id", "campaign_id", "platform", "title", "caption", "video_url")}
        fields["sha256"] = media_hash or file_hash(Path(job["media_path"]))
        fields["campaign"] = self.store.get("campaign", job["campaign_id"])
        fields["account"] = (self.settings.youtube_channel_id if job["platform"] == "youtube"
                             else self.settings.instagram_account_id)
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    def approve(self, job_id: str, reason: str, *, video_url: str | None = None) -> dict:
        job = self.store.get("job", job_id)
        if job["state"] != "rendered":
            raise Blocked("Only a rendered job can be approved; review the actual output first")
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
        job["approval"] = {"digest": self._digest(job), "at": utcnow(), "reason": reason}
        job["state"] = "approved"
        self.store.put("job", job_id, job)
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
        publisher = publisher or await self._publisher(job["platform"])
        expected = (self.settings.youtube_channel_id if job["platform"] == "youtube"
                    else self.settings.instagram_account_id)
        account = await publisher.verify_account()
        if account.get("id") != expected:
            raise Blocked("Authorized account does not match the approved publication target")
        if job["platform"] == "instagram":
            await self._verify_instagram_media(job)
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
                campaign = self.campaign_for(job["campaign_id"], job["platform"])
                self._check_material(job, campaign)
                if (self._digest(job, file_hash(staged_path)) != job["approval"]["digest"]
                        or self.store.get("job", job_id) != job):
                    raise Blocked("Approval or eligibility changed during Instagram processing; publication stopped")
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
