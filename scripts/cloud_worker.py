"""A publication-disabled cloud observation run with explicit durable state.

This is intentionally separate from Workflow.tick: an imported database or a
schedule must never turn a GitHub Actions dry run into an external publication.
Only permitted public campaign observations leave the runner as artifacts.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from content_rewards.config import Settings
from content_rewards.feeds import fetch_campaigns
from content_rewards.models import Campaign
from content_rewards.service import Workflow

ARTIFACT_NAME = "rewards-dry-run-state-v1"
WORKFLOW_PATH = ".github/workflows/cloud-worker.yml"
OBSERVATION_JOB_NAME = "cloud-observation"
MAX_STATE_BYTES = 2_000_000
MAX_FEEDS = 5


class CloudStateError(ValueError):
    """A safe, actionable error without an upstream response or credential."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _public_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
    except (TypeError, ValueError):
        raise CloudStateError("Public source URLs must be valid HTTPS URLs") from None
    if (parsed.scheme != "https" or not host or "." not in host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port not in {None, 443}
            or host.endswith((".local", ".internal", ".localhost", ".test"))):
        raise CloudStateError("Public source URLs must not contain credentials, query strings or private hosts")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise CloudStateError("Public source URLs must not use private addresses")
    return host


def public_campaign(record: dict) -> dict:
    """Discard private attestations/material paths before persistence or ranking."""
    campaign = Campaign.model_validate(record)
    _public_url(str(campaign.source_url))
    campaign.eligibility_verified = False
    campaign.eligibility_evidence = ""
    campaign.payout_eligibility_verified = False
    campaign.payout_evidence = ""
    campaign.requirements_verified = False
    campaign.rights_verified = False
    campaign.evidence_checked_at = None
    campaign.materials = []
    return campaign.model_dump(mode="json")


def validate_state(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise CloudStateError("State envelope has an unsupported schema")
    payload = value["payload"]
    if not isinstance(payload, dict) or set(payload) != {
        "version", "mode", "sequence", "created_at", "previous_run_id", "campaigns", "feeds"
    }:
        raise CloudStateError("State must contain only public observations and feed configuration")
    if value["sha256"] != hashlib.sha256(_json_bytes(payload)).hexdigest():
        raise CloudStateError("State checksum does not match; do not initialize a replacement")
    if type(payload["version"]) is not int or payload["version"] != 1 or payload["mode"] != "dry_run":
        raise CloudStateError("Unsupported cloud state version or mode")
    if type(payload["sequence"]) is not int or payload["sequence"] < 0:
        raise CloudStateError("State sequence is invalid")
    if payload["previous_run_id"] is not None and not re.fullmatch(r"[1-9][0-9]*", str(payload["previous_run_id"])):
        raise CloudStateError("State provenance is invalid")
    try:
        timestamp = datetime.fromisoformat(payload["created_at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError):
        raise CloudStateError("State timestamp must include a timezone") from None
    campaigns = payload["campaigns"]
    feeds = payload["feeds"]
    if not isinstance(campaigns, list) or len(campaigns) > 1000:
        raise CloudStateError("State supports at most 1000 public campaign observations")
    if not isinstance(feeds, list) or len(feeds) > MAX_FEEDS:
        raise CloudStateError("State supports at most five permitted public feeds")
    try:
        normalized = [public_campaign(record) for record in campaigns]
    except Exception:
        raise CloudStateError("State campaign observations are invalid") from None
    if campaigns != normalized:
        raise CloudStateError("Private evidence, verification or material paths must not enter cloud artifacts")
    if len({campaign["id"] for campaign in normalized}) != len(normalized):
        raise CloudStateError("State contains duplicate campaign identifiers")
    seen = set()
    for feed in feeds:
        if not isinstance(feed, dict) or set(feed) != {"id", "url", "allowed_host", "public_permitted_no_cost"}:
            raise CloudStateError("Feed state has an unsupported schema")
        if not isinstance(feed["id"], str) or not re.fullmatch(r"public-feed-[a-f0-9]{12}", feed["id"]):
            raise CloudStateError("Feed identifier is invalid")
        if _public_url(feed["url"]) != feed["allowed_host"] or feed["public_permitted_no_cost"] is not True:
            raise CloudStateError("Feed is not an explicitly permitted public no-cost source")
        if feed["id"] in seen:
            raise CloudStateError("State contains duplicate feed identifiers")
        seen.add(feed["id"])
    return payload


def state_envelope(payload: dict) -> dict:
    envelope = {"payload": payload, "sha256": hashlib.sha256(_json_bytes(payload)).hexdigest()}
    validate_state(envelope)
    if len(_json_bytes(envelope)) > MAX_STATE_BYTES:
        raise CloudStateError("Cloud observation state exceeds its size limit")
    return envelope


def empty_state() -> dict:
    return {"version": 1, "mode": "dry_run", "sequence": 0,
            "created_at": datetime.now(UTC).isoformat(), "previous_run_id": None,
            "campaigns": [], "feeds": []}


def read_state(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_STATE_BYTES:
            raise CloudStateError("Cloud state exceeds its size limit")
        value = json.loads(path.read_bytes())
        return validate_state(value)
    except CloudStateError:
        raise
    except (OSError, ValueError, TypeError):
        raise CloudStateError("Cloud state is missing or corrupt; restoration is required") from None


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(path.name + ".tmp")
    with staged.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False))
    staged.replace(path)


def gh_command(arguments: list[str]) -> str:
    """Use the job's scoped GitHub token without echoing command output on errors."""
    try:
        result = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        raise CloudStateError("GitHub state operation failed; inspect repository authorization and connectivity") from None
    if result.returncode:
        raise CloudStateError("GitHub state operation failed; missing artifacts or access must be resolved before continuing")
    if len(result.stdout.encode()) > 8_000_000:
        raise CloudStateError("GitHub state metadata exceeded its size limit")
    return result.stdout


def _metadata(arguments: list[str], gh) -> dict:
    try:
        value = json.loads(gh(arguments))
    except CloudStateError:
        raise
    except (TypeError, ValueError):
        raise CloudStateError("GitHub returned invalid state metadata") from None
    if not isinstance(value, dict):
        raise CloudStateError("GitHub returned invalid state metadata")
    return value


def _verify_previous(run: dict, branch: str):
    if (run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("head_branch") != branch or run.get("path", "").split("@")[0] != WORKFLOW_PATH):
        raise CloudStateError("The selected previous cloud run was not successful on this branch; inspect before recovery")


def _executed_observation(run: dict, repository: str, gh) -> bool:
    # Disabled schedule gates may create a completed aggregate-success workflow
    # whose only job was skipped. That run never had state and is not a checkpoint.
    if run.get("conclusion") == "skipped":
        return False
    identifier = str(run.get("id", ""))
    if not re.fullmatch(r"[1-9][0-9]*", identifier):
        raise CloudStateError("Previous state run metadata is invalid")
    jobs = _metadata(["api", f"repos/{repository}/actions/runs/{identifier}/jobs"], gh).get("jobs")
    if (not isinstance(jobs, list) or len(jobs) != 1 or not isinstance(jobs[0], dict)
            or jobs[0].get("name") != OBSERVATION_JOB_NAME):
        raise CloudStateError("Previous observation job metadata is unavailable or unsupported")
    return not (jobs[0].get("conclusion") == "skipped" and run.get("conclusion") == "success")


def restore_state(directory: Path, *, repository: str, current_run_id: str, branch: str,
                  initialize: bool = False, previous_run_id: str | None = None, gh=gh_command) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise CloudStateError("A valid GitHub repository identity is required")
    if not re.fullmatch(r"[1-9][0-9]*", current_run_id) or not branch:
        raise CloudStateError("GitHub run identity and branch are required")
    if directory.exists() and any(directory.iterdir()):
        raise CloudStateError("Restore directory is not empty; preserve existing state before continuing")
    directory.mkdir(parents=True, exist_ok=True)
    runs = []
    for page in range(1, 11):
        endpoint = f"repos/{repository}/actions/workflows/cloud-worker.yml/runs?branch={quote(branch, safe='')}&per_page=100&page={page}"
        batch = _metadata(["api", endpoint], gh).get("workflow_runs")
        if not isinstance(batch, list):
            raise CloudStateError("GitHub workflow history is unavailable")
        runs.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise CloudStateError("Workflow history exceeds the restoration limit; inspect known checkpoints before recovery")
    prior = [run for run in runs if str(run.get("id")) != current_run_id and run.get("status") == "completed"]
    if initialize:
        if previous_run_id or any(_executed_observation(run, repository, gh) for run in prior):
            raise CloudStateError("Initialization cannot replace previous cloud state; restore the known artifact")
        payload = empty_state()
        write_json(directory / "state.json", state_envelope(payload))
        return payload
    if previous_run_id:
        if not re.fullmatch(r"[1-9][0-9]*", previous_run_id) or previous_run_id == current_run_id:
            raise CloudStateError("Previous run ID is invalid")
        run = _metadata(["api", f"repos/{repository}/actions/runs/{previous_run_id}"], gh)
        if not _executed_observation(run, repository, gh):
            raise CloudStateError("The selected previous run did not execute an observation job")
    else:
        executed = next((run for run in sorted(prior, key=lambda item: int(item.get("run_number", 0)), reverse=True)
                         if _executed_observation(run, repository, gh)), None)
        if executed is None:
            raise CloudStateError("No prior completed state run exists; explicit first-run initialization is required")
        # Never fall back from a newer failed run or missing artifact to an older ledger.
        run = executed
    _verify_previous(run, branch)
    selected_id = str(run.get("id", ""))
    if not re.fullmatch(r"[1-9][0-9]*", selected_id):
        raise CloudStateError("Previous state run metadata is invalid")
    gh(["run", "download", selected_id, "--repo", repository, "--name", ARTIFACT_NAME, "--dir", str(directory)])
    if {path.name for path in directory.iterdir()} != {"state.json"}:
        raise CloudStateError("State artifact is missing or contains unexpected files")
    payload = read_state(directory / "state.json")
    payload["previous_run_id"] = selected_id
    write_json(directory / "state.json", state_envelope(payload))
    return payload


async def observation_run(state: dict, output: Path, *, public_feed_url: str | None = None,
                          confirm_public_feed: bool = False, fetch=fetch_campaigns) -> dict:
    # Revalidate the entire state before opening a workflow or making a request.
    state = validate_state(state_envelope(state))
    feeds = list(state["feeds"])
    if public_feed_url:
        if not confirm_public_feed:
            raise CloudStateError("A feed requires explicit confirmation that it is public, permitted and no-cost")
        host = _public_url(public_feed_url)
        identifier = "public-feed-" + hashlib.sha256(public_feed_url.encode()).hexdigest()[:12]
        feed = {"id": identifier, "url": public_feed_url, "allowed_host": host, "public_permitted_no_cost": True}
        feeds = [item for item in feeds if item["id"] != identifier] + [feed]
        if len(feeds) > MAX_FEEDS:
            raise CloudStateError("At most five feeds are supported per dry run")
    with tempfile.TemporaryDirectory(prefix="rewards-cloud-observation-") as temporary:
        settings = Settings(database=Path(temporary) / "observations.sqlite", media_root=Path(temporary) / "media",
                            live_publishing=False, admin_token="", youtube_token="", youtube_channel_id="",
                            google_client_id="", google_client_secret="", youtube_refresh_token="",
                            instagram_token="", instagram_account_id="", instagram_api_version="", instagram_media_host="")
        workflow = Workflow(settings)
        workflow.import_campaigns(state["campaigns"], untrusted_feed=True)
        observations = []
        for feed in feeds:
            try:
                records = await fetch(feed["url"], feed["allowed_host"])
                normalized = [public_campaign(record) for record in records]
                workflow.import_campaigns(normalized, untrusted_feed=True)
            except Exception:
                raise CloudStateError("A configured public feed failed verification; no replacement state was saved") from None
            observations.append({"feed_id": feed["id"], "status": "observed", "campaign_count": len(normalized)})
        campaigns = [public_campaign(record) for record in workflow.store.list("campaign")]
        ranking = workflow.rank()
        if any(row["selectable"] for row in ranking):
            raise CloudStateError("Unverified public observations must never become selectable cloud campaigns")
        payload = {"version": 1, "mode": "dry_run", "sequence": state["sequence"] + 1,
                   "created_at": datetime.now(UTC).isoformat(), "previous_run_id": state["previous_run_id"],
                   "campaigns": campaigns, "feeds": feeds}
        report = {"mode": "dry_run", "live_publishing": False, "production_verified": False,
                  "sequence": payload["sequence"], "previous_run_id": payload["previous_run_id"],
                  "discovery": {"status": "observed" if feeds else "blocked_no_permitted_feed", "sources": observations},
                  "campaigns_observed": len(campaigns), "selectable_campaigns": 0, "rankings": ranking,
                  "limitation": "Public observations are unverified; no account authorization, campaign eligibility, publication, tracking or earnings is established"}
        # Export an allowlisted observation envelope, never the database, environment,
        # account identifiers, job approvals, credentials, material paths or earnings.
        write_json(output / "state" / "state.json", state_envelope(payload))
        write_json(output / "report" / "report.json", report)
        return report


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--state-dir", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--state-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "restore":
            state = restore_state(args.state_dir, repository=os.environ.get("GITHUB_REPOSITORY", ""),
                                  current_run_id=os.environ.get("GITHUB_RUN_ID", ""), branch=os.environ.get("GITHUB_REF_NAME", ""),
                                  initialize=os.environ.get("REWARDS_INITIALIZE_STATE") == "true",
                                  previous_run_id=os.environ.get("REWARDS_PREVIOUS_RUN_ID") or None)
            print(json.dumps({"state": "initialized" if state["sequence"] == 0 else "restored", "sequence": state["sequence"]}))
        else:
            report = asyncio.run(observation_run(read_state(args.state_dir / "state.json"), args.output_dir,
                                                 public_feed_url=os.environ.get("REWARDS_PUBLIC_FEED_URL") or None,
                                                 confirm_public_feed=os.environ.get("REWARDS_CONFIRM_PUBLIC_FEED") == "true"))
            # Only counts/status go to logs. Full public ranking is a separate report artifact.
            print(json.dumps({key: report[key] for key in ("mode", "sequence", "campaigns_observed", "selectable_campaigns", "live_publishing")}))
        return 0
    except CloudStateError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
