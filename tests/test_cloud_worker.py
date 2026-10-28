"""Cloud dry runs never deserialize a publishing ledger or reset missing state."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cloud_worker.py"
spec = importlib.util.spec_from_file_location("cloud_worker", SCRIPT)
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


def campaign(**updates):
    return {"id": "public-observation", "title": "Public campaign listing", "source": "manual",
            "source_url": "https://campaigns.example.com/public/1", "rate_per_1000_views_usd": 5,
            "remaining_budget_usd": 1000, "allowed_platforms": ["youtube"],
            "eligibility_verified": True, "eligibility_evidence": "private operator evidence",
            "payout_eligibility_verified": True, "payout_evidence": "private payment evidence",
            "rights_verified": True, "requirements_verified": True,
            "materials": ["/private/approved.mp4"], "evidence_checked_at": "2026-10-28T00:00:00+00:00"} | updates


def prior_run(identifier=12, *, conclusion="success", run_number=1):
    return {"id": identifier, "run_number": run_number, "status": "completed", "conclusion": conclusion,
            "head_branch": "main", "path": cloud.WORKFLOW_PATH}


def restore_args(tmp_path, **updates):
    return {"directory": tmp_path / "restored", "repository": "owner/repository", "current_run_id": "20", "branch": "main"} | updates


class FakeGitHub:
    def __init__(self, runs, payload=None, *, download_error=False, selected=None, skipped_jobs=()):
        self.runs = runs
        self.payload = payload or cloud.empty_state()
        self.download_error = download_error
        self.selected = selected
        self.skipped_jobs = skipped_jobs
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        if arguments[0] == "api":
            if arguments[1].endswith("/jobs"):
                identifier = int(arguments[1].split("/")[-2])
                return json.dumps({"jobs": [{"name": cloud.OBSERVATION_JOB_NAME,
                                              "conclusion": "skipped" if identifier in self.skipped_jobs else "success"}]})
            return json.dumps({"workflow_runs": self.runs} if "/workflows/" in arguments[1] else self.selected)
        if self.download_error:
            raise cloud.CloudStateError("GitHub state operation failed")
        destination = Path(arguments[arguments.index("--dir") + 1])
        cloud.write_json(destination / "state.json", cloud.state_envelope(self.payload))
        return ""


def test_public_observation_discards_private_evidence_rights_and_paths():
    public = cloud.public_campaign(campaign())
    assert public["materials"] == []
    assert public["eligibility_evidence"] == ""
    assert public["payout_evidence"] == ""
    for field in ("eligibility_verified", "rights_verified", "requirements_verified", "payout_eligibility_verified"):
        assert public[field] is False
    assert public["evidence_checked_at"] is None
    assert "/private/" not in json.dumps(public)


@pytest.mark.parametrize("url", ["https://example.com/private?token=credential", "http://example.com/public",
                                      "https://user:secret@example.com/public", "https://127.0.0.1/campaign",
                                      "https://campaigns.internal/campaign", "https://example.com:8080/campaign"])
def test_nonpublic_or_credentialed_campaign_urls_are_rejected(url):
    with pytest.raises((cloud.CloudStateError, ValueError)):
        cloud.public_campaign(campaign(source_url=url))


def test_state_roundtrip_validates_checksum_and_schema(tmp_path):
    payload = cloud.empty_state()
    payload["campaigns"] = [cloud.public_campaign(campaign())]
    envelope = cloud.state_envelope(payload)
    path = tmp_path / "state.json"
    cloud.write_json(path, envelope)
    assert cloud.read_state(path) == payload
    envelope["payload"]["sequence"] = 10
    path.write_text(json.dumps(envelope))
    with pytest.raises(cloud.CloudStateError, match="checksum"):
        cloud.read_state(path)


def test_jobs_and_earnings_cannot_enter_state_even_with_valid_checksum():
    payload = cloud.empty_state() | {"jobs": [{"approval": "secret"}]}
    envelope = {"payload": payload, "sha256": hashlib.sha256(cloud._json_bytes(payload)).hexdigest()}
    with pytest.raises(cloud.CloudStateError, match="only public"):
        cloud.validate_state(envelope)


def test_verified_or_private_campaign_evidence_cannot_enter_artifact():
    payload = cloud.empty_state()
    payload["campaigns"] = [campaign()]
    with pytest.raises(cloud.CloudStateError, match="Private evidence"):
        cloud.state_envelope(payload)


def test_corrupt_or_missing_state_does_not_become_empty(tmp_path):
    for contents in (None, b"not json", b"[]"):
        path = tmp_path / "state.json"
        if contents:
            path.write_bytes(contents)
        with pytest.raises(cloud.CloudStateError):
            cloud.read_state(path)


def test_first_run_requires_explicit_initialization(tmp_path):
    gh = FakeGitHub([])
    with pytest.raises(cloud.CloudStateError, match="explicit first-run"):
        cloud.restore_state(**restore_args(tmp_path), gh=gh)
    assert all(call[0] == "api" for call in gh.calls)


def test_explicit_first_initialization_writes_valid_empty_state(tmp_path):
    gh = FakeGitHub([prior_run(20)])
    state = cloud.restore_state(**restore_args(tmp_path), gh=gh, initialize=True)
    assert state["sequence"] == 0 and state["campaigns"] == []
    assert cloud.read_state(tmp_path / "restored/state.json") == state
    assert len(gh.calls) == 1


def test_initialization_cannot_replace_existing_completed_run(tmp_path):
    with pytest.raises(cloud.CloudStateError, match="cannot replace"):
        cloud.restore_state(**restore_args(tmp_path), gh=FakeGitHub([prior_run()]), initialize=True)


def test_restore_downloads_exact_latest_successful_run_and_sets_provenance(tmp_path):
    gh = FakeGitHub([prior_run(8, run_number=1), prior_run(12, run_number=2), prior_run(20, run_number=3)])
    state = cloud.restore_state(**restore_args(tmp_path), gh=gh)
    assert gh.calls[-1][:3] == ["run", "download", "12"]
    assert state["previous_run_id"] == "12"


def test_newer_failed_run_prevents_silent_fallback_to_old_ledger(tmp_path):
    gh = FakeGitHub([prior_run(12, conclusion="failure", run_number=2), prior_run(8, run_number=1)])
    with pytest.raises(cloud.CloudStateError, match="not successful"):
        cloud.restore_state(**restore_args(tmp_path), gh=gh)
    assert all(call[0] != "run" for call in gh.calls)


def test_explicitly_skipped_schedule_runs_do_not_block_first_initialization(tmp_path):
    gh = FakeGitHub([prior_run(12, conclusion="skipped")])
    assert cloud.restore_state(**restore_args(tmp_path), gh=gh, initialize=True)["sequence"] == 0


def test_successful_workflow_with_gated_skipped_job_is_not_a_state_checkpoint(tmp_path):
    gh = FakeGitHub([prior_run(15, run_number=2), prior_run(12, run_number=1)], skipped_jobs={15})
    state = cloud.restore_state(**restore_args(tmp_path), gh=gh)
    assert state["previous_run_id"] == "12"
    assert gh.calls[-1][:3] == ["run", "download", "12"]


def test_gated_scheduled_runs_allow_first_explicit_initialization(tmp_path):
    gh = FakeGitHub([prior_run(15, run_number=2), prior_run(12, run_number=1)], skipped_jobs={12, 15})
    state = cloud.restore_state(**restore_args(tmp_path), gh=gh, initialize=True)
    assert state["sequence"] == 0


def test_cancelled_workflow_is_not_ignored_as_a_disabled_schedule(tmp_path):
    gh = FakeGitHub([prior_run(15, conclusion="cancelled", run_number=2), prior_run(12, run_number=1)], skipped_jobs={15})
    with pytest.raises(cloud.CloudStateError, match="not successful"):
        cloud.restore_state(**restore_args(tmp_path), gh=gh)


def test_missing_or_expired_artifact_prevents_replacement_state(tmp_path):
    gh = FakeGitHub([prior_run()], download_error=True)
    with pytest.raises(cloud.CloudStateError, match="operation failed"):
        cloud.restore_state(**restore_args(tmp_path), gh=gh)
    assert not (tmp_path / "restored/state.json").exists()


def test_explicit_previous_run_requires_matching_workflow_branch_and_success(tmp_path):
    selected = prior_run(9) | {"head_branch": "other"}
    gh = FakeGitHub([prior_run(12, conclusion="failure")], selected=selected)
    with pytest.raises(cloud.CloudStateError, match="not successful"):
        cloud.restore_state(**restore_args(tmp_path), gh=gh, previous_run_id="9")
    selected["head_branch"] = "main"
    state = cloud.restore_state(**restore_args(tmp_path), gh=gh, previous_run_id="9")
    assert state["previous_run_id"] == "9"


def test_nonempty_restore_directory_is_preserved(tmp_path):
    directory = tmp_path / "restored"
    directory.mkdir()
    user_file = directory / "keep.txt"
    user_file.write_text("keep")
    with pytest.raises(cloud.CloudStateError, match="not empty"):
        cloud.restore_state(**restore_args(tmp_path), gh=FakeGitHub([]), initialize=True)
    assert user_file.read_text() == "keep"


async def test_no_feed_is_reported_blocked_and_cannot_publish(tmp_path, monkeypatch):
    async def unexpected(*args):
        pytest.fail("No publishing or general schedule tick is permitted in cloud dry run")
    monkeypatch.setattr(cloud.Workflow, "publish", unexpected)
    monkeypatch.setattr(cloud.Workflow, "tick", unexpected)
    monkeypatch.setenv("REWARDS_LIVE_PUBLISHING", "true")
    monkeypatch.setenv("YOUTUBE_ACCESS_TOKEN", "never-artifact-this-token")
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "never-artifact-this-account")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "never-artifact-this-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "never-artifact-this-secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "never-artifact-this-refresh-token")
    initialize = cloud.Workflow.__init__
    def inspect_settings(self, settings):
        assert not settings.live_publishing
        assert not settings.youtube_token and not settings.youtube_refresh_token
        assert not settings.google_client_id and not settings.google_client_secret
        assert not settings.youtube_channel_id and not settings.instagram_account_id
        initialize(self, settings)
    monkeypatch.setattr(cloud.Workflow, "__init__", inspect_settings)
    report = await cloud.observation_run(cloud.empty_state(), tmp_path)
    assert report["discovery"]["status"] == "blocked_no_permitted_feed"
    assert not report["live_publishing"] and not report["production_verified"]
    assert report["sequence"] == 1 and report["selectable_campaigns"] == 0
    files = list(tmp_path.rglob("*.json"))
    assert {path.name for path in files} == {"state.json", "report.json"}
    assert all("never-artifact" not in path.read_text() for path in files)


async def test_public_feed_requires_explicit_permitted_no_cost_confirmation(tmp_path):
    with pytest.raises(cloud.CloudStateError, match="confirmation"):
        await cloud.observation_run(cloud.empty_state(), tmp_path, public_feed_url="https://feeds.example.com/campaigns.json")
    assert not list(tmp_path.iterdir())


async def test_permitted_feed_observations_are_ranked_but_never_self_verified(tmp_path):
    calls = []
    async def fetch(url, host):
        calls.append((url, host))
        return [campaign()]
    report = await cloud.observation_run(cloud.empty_state(), tmp_path, public_feed_url="https://feeds.example.com/campaigns.json",
                                         confirm_public_feed=True, fetch=fetch)
    assert calls == [("https://feeds.example.com/campaigns.json", "feeds.example.com")]
    assert report["discovery"]["status"] == "observed" and report["campaigns_observed"] == 1
    assert report["selectable_campaigns"] == 0 and not report["rankings"][0]["selectable"]
    state = cloud.read_state(tmp_path / "state/state.json")
    assert state["sequence"] == 1 and len(state["feeds"]) == 1
    assert state["campaigns"][0]["materials"] == []
    assert "private operator evidence" not in json.dumps(state)


async def test_failed_feed_leaves_no_new_state_instead_of_partial_snapshot(tmp_path):
    async def fail(url, host):
        raise RuntimeError("Untrusted upstream body could include credentials")
    with pytest.raises(cloud.CloudStateError, match="no replacement state") as error:
        await cloud.observation_run(cloud.empty_state(), tmp_path, public_feed_url="https://feeds.example.com/campaigns.json",
                                     confirm_public_feed=True, fetch=fail)
    assert "credentials" not in str(error.value)
    assert not list(tmp_path.iterdir())


async def test_public_state_survives_next_runner_without_private_workflow_data(tmp_path):
    first = tmp_path / "first"
    await cloud.observation_run(cloud.empty_state(), first)
    restored = cloud.read_state(first / "state/state.json")
    restored["previous_run_id"] = "123"
    second = tmp_path / "second"
    report = await cloud.observation_run(restored, second)
    assert report["sequence"] == 2 and report["previous_run_id"] == "123"
    assert cloud.read_state(second / "state/state.json")["sequence"] == 2
