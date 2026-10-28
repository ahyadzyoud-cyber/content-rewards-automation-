"""Real local Git checkpoints; no remote service, paid storage or old suite rerun."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/git_cloud_worker.py"
spec = importlib.util.spec_from_file_location("git_cloud_worker", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def git(repository, *arguments, data=None, check=True):
    environment = dict(os.environ, GIT_AUTHOR_NAME="Local fixture", GIT_COMMITTER_NAME="Local fixture",
                       GIT_AUTHOR_EMAIL="fixture@example.com", GIT_COMMITTER_EMAIL="fixture@example.com",
                       GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(repository), *arguments], input=data, capture_output=True,
                          env=environment, check=check, timeout=15)


def checkout(directory, remote):
    directory.mkdir()
    git(directory, "init", "--initial-branch=main")
    git(directory, "remote", "add", "origin", str(remote))
    git(directory, "fetch", "origin", "main")
    git(directory, "reset", "--soft", "FETCH_HEAD")
    # Populate a fixture's own main checkout; production code never uses reset.
    git(directory, "checkout", "HEAD", "--", "README.md")
    return directory


@pytest.fixture
def repository(tmp_path):
    remote = tmp_path / "origin.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    work = tmp_path / "source"
    work.mkdir()
    git(work, "init", "--initial-branch=main")
    (work / "README.md").write_text("Fixture source, never replaced by observations\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "Fixture source")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "origin", "main")
    return work, remote


async def observation(state, tmp_path):
    report = await worker.cloud.observation_run(state, tmp_path)
    updated = worker.cloud.read_state(tmp_path / "state/state.json")
    return updated, report


def raw_checkpoint(repository, files, *, parent=None, message=None, modes=None):
    entries = []
    for name, value in sorted(files.items()):
        blob = git(repository, "hash-object", "-w", "--stdin", data=value).stdout.decode().strip()
        mode = (modes or {}).get(name, "100644")
        entries.append(f"{mode} blob {blob}\t{name}\n")
    tree = git(repository, "mktree", data="".join(entries).encode()).stdout.decode().strip()
    arguments = ["commit-tree", tree]
    if parent:
        arguments.extend(["-p", parent])
    body = message or "Fixture checkpoint\n\nObservation-Sequence: 1\nGitHub-Run-ID: 100\n"
    commit = git(repository, *arguments, data=body.encode()).stdout.decode().strip()
    git(repository, "push", "origin", commit + ":" + worker.REMOTE_REF)
    return commit


def checkpoint_files(repository, commit):
    return {name: git(repository, "show", commit + ":" + name).stdout for name in ("state.json", "report.json")}


def test_missing_branch_requires_explicit_initialization(repository):
    work, _ = repository
    with pytest.raises(worker.GitStateError, match="explicit first-run"):
        worker.restore_checkpoint(work)
    state, parent = worker.restore_checkpoint(work, initialize=True)
    assert state["sequence"] == 0 and state["campaigns"] == [] and parent is None


async def test_two_runs_restore_checkpoint_and_preserve_main_worktree(repository, monkeypatch):
    work, remote = repository
    original_head = git(work, "rev-parse", "HEAD").stdout
    original_index = git(work, "write-tree").stdout
    original_config = (work / ".git/config").read_bytes()
    monkeypatch.setenv("REWARDS_LIVE_PUBLISHING", "true")
    monkeypatch.setenv("YOUTUBE_ACCESS_TOKEN", "never-persist-this-token")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "never-persist-this-refresh")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "never-persist-this-secret")
    monkeypatch.setenv("WHOP_API_KEY", "never-persist-this-key")
    first = await worker.run_once(work, run_id="100", initialize=True)
    second = await worker.run_once(work, run_id="101")
    assert first["sequence"] == 1 and second["sequence"] == 2
    assert second["live_publishing"] is False and second["production_verified"] is False
    assert second["discovery_status"] == "blocked_no_permitted_feed"
    assert git(work, "rev-parse", "HEAD").stdout == original_head
    assert git(work, "write-tree").stdout == original_index
    assert git(work, "status", "--porcelain").stdout == b""
    assert (work / ".git/config").read_bytes() == original_config
    assert git(remote, "rev-parse", "main").stdout == original_head
    files = checkpoint_files(work, second["checkpoint_commit"])
    state = worker.cloud.validate_state(json.loads(files["state.json"]))
    assert state["previous_run_id"] == "100"
    assert json.loads(files["report.json"])["previous_run_id"] == "100"
    assert all(b"never-persist" not in value for value in files.values())
    restored, tip = worker.restore_checkpoint(work)
    assert restored["sequence"] == 2 and restored["previous_run_id"] == "101"
    assert tip == second["checkpoint_commit"]


async def test_initialization_never_replaces_existing_checkpoint(repository):
    work, _ = repository
    first = await worker.run_once(work, run_id="100", initialize=True)
    with pytest.raises(worker.GitStateError, match="cannot replace"):
        await worker.run_once(work, run_id="101", initialize=True)
    assert worker.remote_head(work) == first["checkpoint_commit"]


def test_remote_access_error_is_not_missing_branch(repository, tmp_path):
    work, _ = repository
    git(work, "remote", "set-url", "origin", str(tmp_path / "not-a-repository"))
    with pytest.raises(worker.GitStateError, match="Git checkpoint operation failed"):
        worker.restore_checkpoint(work, initialize=True)


async def test_stale_writer_normal_push_rejected_without_overwriting_latest(repository, tmp_path):
    work, remote = repository
    await worker.run_once(work, run_id="100", initialize=True)
    competitor = checkout(tmp_path / "competitor", remote)
    stale_state, stale_parent = worker.restore_checkpoint(competitor)
    newer = await worker.run_once(work, run_id="101")
    updated, report = await observation(stale_state, tmp_path / "competing-observation")
    with pytest.raises(worker.GitStateError, match="concurrent changes"):
        worker.commit_checkpoint(competitor, stale_parent, updated, report, run_id="102")
    assert worker.remote_head(work) == newer["checkpoint_commit"]
    assert git(competitor, "status", "--porcelain").stdout == b""


async def test_competing_initializers_cannot_overwrite_first_root_checkpoint(repository, tmp_path):
    work, remote = repository
    competitor = checkout(tmp_path / "competitor", remote)
    state_a, parent_a = worker.restore_checkpoint(work, initialize=True)
    state_b, parent_b = worker.restore_checkpoint(competitor, initialize=True)
    updated_a, report_a = await observation(state_a, tmp_path / "a")
    updated_b, report_b = await observation(state_b, tmp_path / "b")
    first = worker.commit_checkpoint(work, parent_a, updated_a, report_a, run_id="100")
    with pytest.raises(worker.GitStateError, match="concurrent changes"):
        worker.commit_checkpoint(competitor, parent_b, updated_b, report_b, run_id="101")
    assert worker.remote_head(work) == first


@pytest.mark.parametrize("damage", ["checksum", "missing_state", "unexpected_file", "symlink", "oversized_blob", "producer"])
async def test_invalid_checkpoint_fails_closed(repository, damage):
    work, _ = repository
    first = await worker.run_once(work, run_id="100", initialize=True)
    files = checkpoint_files(work, first["checkpoint_commit"])
    modes = None
    message = None
    if damage == "checksum":
        value = json.loads(files["state.json"])
        value["payload"]["sequence"] = 900
        files["state.json"] = json.dumps(value).encode()
    elif damage == "missing_state":
        files.pop("state.json")
    elif damage == "unexpected_file":
        files["private.sqlite"] = b"not allowed"
    elif damage == "symlink":
        modes = {"state.json": "120000"}
    elif damage == "oversized_blob":
        files["state.json"] = b"x" * (worker.MAX_CHECKPOINT_BYTES + 1)
    else:
        message = "No producer evidence\n"
    tip = raw_checkpoint(work, files, parent=first["checkpoint_commit"], modes=modes, message=message)
    with pytest.raises(worker.GitStateError):
        worker.restore_checkpoint(work)
    assert worker.remote_head(work) == tip
    assert git(work, "status", "--porcelain").stdout == b""


async def test_report_cannot_contain_private_extra_fields_or_selectable_claim(repository, tmp_path):
    work, _ = repository
    state, report = await observation(worker.cloud.empty_state(), tmp_path)
    report["account_token"] = "not allowed"
    with pytest.raises(worker.GitStateError, match="public dry-run"):
        worker.commit_checkpoint(work, None, state, report, run_id="100")
    report.pop("account_token")
    report["production_verified"] = True
    with pytest.raises(worker.GitStateError, match="public dry-run"):
        worker.commit_checkpoint(work, None, state, report, run_id="100")
    assert worker.remote_head(work) is None


async def test_oversized_combined_checkpoint_is_not_pushed(repository, tmp_path):
    work, _ = repository
    state, report = await observation(worker.cloud.empty_state(), tmp_path)
    report["limitation"] = "x" * worker.MAX_CHECKPOINT_BYTES
    with pytest.raises(worker.GitStateError, match="128 KiB"):
        worker.commit_checkpoint(work, None, state, report, run_id="100")
    assert worker.remote_head(work) is None


@pytest.mark.parametrize("run_id", ["", "0", "-1", "1;bad", "not-numeric"])
async def test_invalid_run_identity_rejected_before_git(repository, run_id):
    work, _ = repository
    with pytest.raises(worker.GitStateError, match="valid GitHub run ID"):
        await worker.run_once(work, run_id=run_id, initialize=True)
    assert worker.remote_head(work) is None


async def test_no_provider_network_calls_without_explicit_public_feed(repository):
    work, _ = repository
    async def unexpected(*args):
        pytest.fail("A no-feed cloud observer must not query providers")
    result = await worker.run_once(work, run_id="100", initialize=True, fetch=unexpected)
    assert result["campaigns_observed"] == 0
    assert result["discovery_status"] == "blocked_no_permitted_feed"
