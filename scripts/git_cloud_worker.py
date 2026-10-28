"""Persist public, publication-disabled observations on a small Git checkpoint branch.

The source checkout and index are never switched or rewritten. Git's ordinary
non-force push protects concurrent checkpoint writers. No private application
database, account credentials, approvals or earnings are written to this branch.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("rewards_observation", Path(__file__).with_name("cloud_worker.py"))
cloud = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cloud)

STATE_BRANCH = "rewards-observation-state"
REMOTE_REF = "refs/heads/" + STATE_BRANCH
TRACKING_REF = "refs/remotes/origin/" + STATE_BRANCH
MAX_CHECKPOINT_BYTES = 128 * 1024
OBJECT_ID = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})")
REPORT_FIELDS = {
    "mode", "live_publishing", "production_verified", "sequence", "previous_run_id",
    "discovery", "campaigns_observed", "selectable_campaigns", "rankings", "limitation",
}


class GitStateError(ValueError):
    """A sanitized checkpoint failure; never substitute an empty ledger."""


def _git(repository: Path, arguments: list[str], *, data: bytes | None = None,
         allow_missing: bool = False) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "github-actions[bot]",
                        "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                        "GIT_COMMITTER_NAME": "github-actions[bot]",
                        "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"})
    try:
        result = subprocess.run(["git", "-C", str(repository), *arguments], input=data,
                                capture_output=True, timeout=90, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        raise GitStateError("Git checkpoint operation failed; check authorization and connectivity") from None
    if result.returncode and not (allow_missing and result.returncode == 2):
        raise GitStateError("Git checkpoint operation failed; preserve the current checkpoint and inspect authorization or concurrent changes")
    return result


def _object_id(value: bytes) -> str:
    try:
        identifier = value.decode("ascii").strip()
    except UnicodeError:
        raise GitStateError("Git returned an invalid object identifier") from None
    if not OBJECT_ID.fullmatch(identifier):
        raise GitStateError("Git returned an invalid object identifier")
    return identifier


def remote_head(repository: Path) -> str | None:
    result = _git(repository, ["ls-remote", "--exit-code", "origin", REMOTE_REF], allow_missing=True)
    if result.returncode == 2:
        if result.stdout.strip():
            raise GitStateError("Missing-branch response contained unexpected data")
        return None
    try:
        lines = result.stdout.decode("ascii").strip().splitlines()
        if len(lines) != 1:
            raise ValueError
        identifier, reference = lines[0].split("\t")
        if reference != REMOTE_REF:
            raise ValueError
    except (UnicodeError, ValueError):
        raise GitStateError("Git returned unexpected checkpoint branch metadata") from None
    return _object_id(identifier.encode())


def _blob(repository: Path, identifier: str) -> bytes:
    try:
        size = int(_git(repository, ["cat-file", "-s", identifier]).stdout)
    except ValueError:
        raise GitStateError("Checkpoint object size is invalid") from None
    if not 0 < size <= MAX_CHECKPOINT_BYTES:
        raise GitStateError("Checkpoint object exceeds the 128 KiB limit")
    value = _git(repository, ["cat-file", "blob", identifier]).stdout
    if len(value) != size:
        raise GitStateError("Checkpoint object is incomplete")
    return value


def _json(value: bytes) -> dict:
    try:
        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError):
        raise GitStateError("Checkpoint JSON is invalid; do not initialize a replacement") from None


def _validate_report(report: dict, state: dict):
    if (set(report) != REPORT_FIELDS or report.get("mode") != "dry_run"
            or report.get("live_publishing") is not False or report.get("production_verified") is not False
            or type(report.get("sequence")) is not int or type(report.get("campaigns_observed")) is not int
            or report.get("sequence") != state["sequence"]
            or report.get("previous_run_id") != state["previous_run_id"]
            or report.get("campaigns_observed") != len(state["campaigns"])
            or type(report.get("selectable_campaigns")) is not int or report["selectable_campaigns"] != 0
            or not isinstance(report.get("rankings"), list) or not isinstance(report.get("limitation"), str)):
        raise GitStateError("Checkpoint report is not a matching public dry-run report")
    from content_rewards.models import CampaignScore
    try:
        rankings = [CampaignScore.model_validate(item) for item in report["rankings"]]
    except ValueError:
        raise GitStateError("Checkpoint ranking report is invalid") from None
    if (any(item.selectable for item in rankings)
            or {item.campaign_id for item in rankings} != {item["id"] for item in state["campaigns"]}
            or len(rankings) != len(state["campaigns"])):
        raise GitStateError("A cloud observation must not authorize campaign selection")
    discovery = report.get("discovery")
    if (not isinstance(discovery, dict) or set(discovery) != {"status", "sources"}
            or discovery["status"] not in {"observed", "blocked_no_permitted_feed"}
            or not isinstance(discovery["sources"], list)):
        raise GitStateError("Checkpoint discovery report is invalid")
    sources = discovery["sources"]
    expected_status = "observed" if state["feeds"] else "blocked_no_permitted_feed"
    if discovery["status"] != expected_status:
        raise GitStateError("Checkpoint discovery status does not match its feed configuration")
    if len(sources) != len(state["feeds"]):
        raise GitStateError("Checkpoint discovery sources do not match the public feeds")
    for source, feed in zip(sources, state["feeds"], strict=True):
        if (not isinstance(source, dict) or set(source) != {"feed_id", "status", "campaign_count"}
                or source["feed_id"] != feed["id"] or source["status"] != "observed"
                or type(source["campaign_count"]) is not int or source["campaign_count"] < 0):
            raise GitStateError("Checkpoint feed report is invalid")


def _producer_run(repository: Path, commit: str, sequence: int) -> str:
    message = _git(repository, ["show", "--no-patch", "--format=%B", commit]).stdout
    if len(message) > 4096:
        raise GitStateError("Checkpoint commit metadata exceeds its limit")
    try:
        text = message.decode("ascii")
    except UnicodeError:
        raise GitStateError("Checkpoint commit metadata is invalid") from None
    runs = re.findall(r"^GitHub-Run-ID: ([1-9][0-9]*)$", text, re.MULTILINE)
    sequences = re.findall(r"^Observation-Sequence: ([1-9][0-9]*)$", text, re.MULTILINE)
    if len(runs) != 1 or len(sequences) != 1 or int(sequences[0]) != sequence:
        raise GitStateError("Checkpoint producer metadata is missing or inconsistent")
    return runs[0]


def restore_checkpoint(repository: Path, *, initialize: bool = False) -> tuple[dict, str | None]:
    head = remote_head(repository)
    if head is None:
        if not initialize:
            raise GitStateError("Observation state branch is missing; explicit first-run initialization is required")
        return cloud.empty_state(), None
    if initialize:
        raise GitStateError("Initialization cannot replace the existing observation checkpoint")
    _git(repository, ["fetch", "--no-tags", "--no-write-fetch-head", "origin", REMOTE_REF + ":" + TRACKING_REF])
    fetched = _object_id(_git(repository, ["rev-parse", "--verify", TRACKING_REF + "^{commit}"]).stdout)
    if fetched != head:
        raise GitStateError("Checkpoint branch changed during restoration; restore its new tip before continuing")
    entries = _git(repository, ["ls-tree", "-z", head]).stdout.split(b"\0")
    objects = {}
    try:
        for entry in entries:
            if not entry:
                continue
            metadata, name = entry.split(b"\t")
            mode, kind, identifier = metadata.split(b" ")
            if mode != b"100644" or kind != b"blob" or name not in {b"state.json", b"report.json"}:
                raise ValueError
            objects[name.decode("ascii")] = _object_id(identifier)
    except (ValueError, UnicodeError):
        raise GitStateError("Checkpoint tree contains unexpected files or non-regular objects") from None
    if set(objects) != {"state.json", "report.json"}:
        raise GitStateError("Checkpoint tree is missing its state or report")
    state_bytes = _blob(repository, objects["state.json"])
    report_bytes = _blob(repository, objects["report.json"])
    if len(state_bytes) + len(report_bytes) > MAX_CHECKPOINT_BYTES:
        raise GitStateError("Combined checkpoint exceeds the 128 KiB limit")
    try:
        state = cloud.validate_state(_json(state_bytes))
        _validate_report(_json(report_bytes), state)
    except cloud.CloudStateError:
        raise GitStateError("Checkpoint state is corrupt or contains unsupported private data") from None
    state["previous_run_id"] = _producer_run(repository, head, state["sequence"])
    return state, head


def commit_checkpoint(repository: Path, parent: str | None, state: dict, report: dict, *, run_id: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise GitStateError("A valid GitHub run ID is required")
    try:
        envelope = cloud.state_envelope(state)
        _validate_report(report, state)
        state_bytes = cloud._json_bytes(envelope) + b"\n"
        report_bytes = cloud._json_bytes(report) + b"\n"
    except cloud.CloudStateError:
        raise GitStateError("Only valid public observation state may be committed") from None
    if len(state_bytes) + len(report_bytes) > MAX_CHECKPOINT_BYTES:
        raise GitStateError("Combined checkpoint exceeds the 128 KiB limit; no state was pushed")
    if parent is not None and not OBJECT_ID.fullmatch(parent):
        raise GitStateError("Checkpoint parent is invalid")
    state_object = _object_id(_git(repository, ["hash-object", "-w", "--stdin"], data=state_bytes).stdout)
    report_object = _object_id(_git(repository, ["hash-object", "-w", "--stdin"], data=report_bytes).stdout)
    tree_input = f"100644 blob {report_object}\treport.json\n100644 blob {state_object}\tstate.json\n".encode()
    tree = _object_id(_git(repository, ["mktree"], data=tree_input).stdout)
    message = (f"Record public observation checkpoint\n\nObservation-Sequence: {state['sequence']}\n"
               f"GitHub-Run-ID: {run_id}\n").encode()
    arguments = ["commit-tree", tree]
    if parent is not None:
        arguments.extend(["-p", parent])
    commit = _object_id(_git(repository, arguments, data=message).stdout)
    # This intentionally has no --force/lease/reset. A concurrent successful
    # writer makes this push non-fast-forward and leaves its checkpoint intact.
    _git(repository, ["push", "origin", commit + ":" + REMOTE_REF])
    return commit


async def run_once(repository: Path, *, run_id: str, initialize: bool = False,
                   public_feed_url: str | None = None, confirm_public_feed: bool = False,
                   fetch=cloud.fetch_campaigns) -> dict:
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise GitStateError("A valid GitHub run ID is required")
    state, parent = restore_checkpoint(repository, initialize=initialize)
    with tempfile.TemporaryDirectory(prefix="rewards-git-observation-") as temporary:
        output = Path(temporary)
        report = await cloud.observation_run(state, output, public_feed_url=public_feed_url,
                                             confirm_public_feed=confirm_public_feed, fetch=fetch)
        updated = cloud.read_state(output / "state" / "state.json")
        commit = commit_checkpoint(repository, parent, updated, report, run_id=run_id)
    return {"mode": "dry_run", "sequence": updated["sequence"], "checkpoint_commit": commit,
            "campaigns_observed": report["campaigns_observed"], "discovery_status": report["discovery"]["status"],
            "live_publishing": False, "production_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-dir", type=Path, default=Path.cwd())
    parser.add_argument("--initialize-state", action="store_true")
    options = parser.parse_args()
    try:
        report = asyncio.run(run_once(options.repository_dir, run_id=os.environ.get("GITHUB_RUN_ID", ""),
                                      initialize=options.initialize_state,
                                      public_feed_url=os.environ.get("REWARDS_PUBLIC_FEED_URL") or None,
                                      confirm_public_feed=os.environ.get("REWARDS_CONFIRM_PUBLIC_FEED") == "true"))
        print(json.dumps(report))
        return 0
    except (GitStateError, cloud.CloudStateError) as exc:
        print(json.dumps({"error": str(exc), "live_publishing": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
