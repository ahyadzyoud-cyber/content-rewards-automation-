"""Official deployment API boundaries; all requests stay in a local mock transport."""
import importlib.util
import json
import sqlite3
from email import policy
from email.parser import BytesParser
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/deploy_whop.py"
spec = importlib.util.spec_from_file_location("whop_deploy", SCRIPT)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

ACCOUNT = "a" * 32
DATABASE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORIGIN = "https://content-rewards-whop.fixture-owner.workers.dev"
TOKEN = "private-cloudflare-proxy-binding"


def envelope(result, **extra):
    return httpx.Response(200, json={"success": True, "result": result} | extra)


class Provider:
    """Stateful mock keeps real multipart/API contracts and a private remote store."""

    def __init__(self):
        self.requests = []
        self.subscriptions = []
        self.accounts = [{"id": ACCOUNT}]
        self.databases = []
        self.bindings = None
        self.subdomain = {"enabled": False, "previews_enabled": False}
        self.schedules = []
        self.private_rows = 0
        self.uploads = []
        self.fail_upload = False
        self.fail_schedule_verification = False

    def __call__(self, request):
        self.requests.append(request)
        assert request.url.host == "api.cloudflare.com"
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert TOKEN not in str(request.url)
        prefix = "/client/v4/accounts/" + ACCOUNT
        path = request.url.path
        if request.method == "GET":
            if path == "/client/v4/accounts":
                return envelope(self.accounts)
            if path == prefix + "/subscriptions":
                return envelope(self.subscriptions)
            if path == prefix + "/workers/subdomain":
                return envelope({"subdomain": "fixture-owner"})
            if path == prefix + "/workers/scripts":
                return envelope([] if self.bindings is None else [{"id": deploy.WORKER_NAME}])
            if path == prefix + "/d1/database":
                return envelope(self.databases)
            if path.endswith("/settings"):
                return envelope({"bindings": self.bindings})
            if path.endswith("/subdomain"):
                return envelope(self.subdomain)
            if path.endswith("/schedules"):
                return envelope({"schedules": [] if self.fail_schedule_verification else self.schedules})
        if request.method == "POST" and path == prefix + "/d1/database":
            assert json.loads(request.content) == {"name": deploy.DATABASE_NAME}
            self.databases = [{"uuid": DATABASE, "name": deploy.DATABASE_NAME}]
            return envelope(self.databases[0])
        if request.method == "POST" and path.endswith("/query"):
            sql = json.loads(request.content)["sql"]
            assert "DROP " not in sql.upper() and "DELETE " not in sql.upper()
            if sql.startswith("SELECT "):
                return envelope([{"success": True, "results": [{"private_rows": self.private_rows}]}])
            assert "CREATE TABLE IF NOT EXISTS whop_credentials" in sql
            return envelope([{"success": True, "results": []}])
        if request.method == "PUT" and path == prefix + "/workers/scripts/" + deploy.WORKER_NAME:
            # Parse the actual multipart body instead of mocking away transport.
            message = BytesParser(policy=policy.default).parsebytes(
                ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode() + request.content)
            parts = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
            metadata = json.loads(parts["metadata"].get_payload(decode=True))
            assert parts["worker.mjs"].get_content_type() == "application/javascript+module"
            assert metadata["main_module"] == "worker.mjs"
            assert metadata["logpush"] is False and metadata["observability"] == {"enabled": False}
            assert metadata["keep_bindings"] == ["secret_text"]
            self.uploads.append(metadata)
            preserved = [] if self.bindings is None else [binding for binding in self.bindings if binding["type"] == "secret_text"]
            self.bindings = metadata["bindings"] + preserved
            if self.fail_upload:
                # Simulate an accepted upload with an uncertain HTTP result.
                raise httpx.ReadTimeout("private-upstream-token", request=request)
            return envelope({"id": deploy.WORKER_NAME})
        if request.method == "POST" and path.endswith("/subdomain"):
            self.subdomain = json.loads(request.content)
            return envelope(self.subdomain)
        if request.method == "PUT" and path.endswith("/schedules"):
            self.schedules = json.loads(request.content)
            return envelope({"schedules": self.schedules})
        pytest.fail(f"Unexpected deployment operation: {request.method} {path}")


def run(provider, path, *, apply=False, **environment):
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        return deploy.deploy({"CLOUDFLARE_API_TOKEN": TOKEN} | environment,
                             apply=apply, client=client, state_path=path)


def test_missing_token_is_blocked_before_network(tmp_path):
    def unexpected(request):
        pytest.fail("Missing deployment authorization must not initiate HTTPS")
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(deploy.DeploymentBlocked, match="secure environment"):
            deploy.deploy({}, apply=True, client=client, state_path=tmp_path / "state.json")


def test_preflight_is_readonly_and_does_not_claim_actual_callback_is_live(tmp_path):
    provider = Provider()
    state = tmp_path / "state.json"
    result = run(provider, state)
    assert result["callback"] == ORIGIN + "/oauth/callback"
    assert result["status"] == "preflight_passed"
    assert result["resources_changed"] is False
    assert result["authorization_complete"] is False
    assert result["live_publishing"] is False
    assert all(request.method == "GET" for request in provider.requests)
    assert not state.exists() and provider.bindings is None


@pytest.mark.parametrize("subscription", [
    {"state": "Provisioned", "price": 5, "rate_plan": {"id": "workers_paid"}},
    {"state": "Trial", "price": 0, "rate_plan": {"id": "free"}},
    {"state": "Provisioned", "price": 0, "rate_plan": {"id": "unknown_metered"}},
    {"state": "Paid", "price": True, "rate_plan": {"id": "free"}},
    {"state": "Paid", "price": 0, "rate_plan": {"id": "free", "is_contract": True}},
    {"state": {"malformed": True}, "price": 0, "rate_plan": {"id": "free"}},
    {"state": "Paid", "price": 0, "rate_plan": {"id": ["free"]}},
    {"state": "Paid", "price": 0, "rate_plan": {"id": "free", "is_contract": {"unknown": True}}},
])
def test_paid_trial_or_unknown_account_never_changes_resources(tmp_path, subscription):
    provider = Provider()
    provider.subscriptions = [subscription]
    with pytest.raises(deploy.DeploymentBlocked, match="paid, trial, or unknown"):
        run(provider, tmp_path / "state.json", apply=True)
    assert all(request.method == "GET" for request in provider.requests)


def test_multiple_accounts_require_explicit_existing_account_selection(tmp_path):
    provider = Provider()
    provider.accounts.append({"id": "b" * 32})
    with pytest.raises(deploy.DeploymentBlocked, match="Select the existing free account"):
        run(provider, tmp_path / "state.json")
    result = run(provider, tmp_path / "state.json", CLOUDFLARE_ACCOUNT_ID=ACCOUNT)
    assert result["free_account_verified"] is True


def test_first_deployment_and_redeployment_preserve_key_database_and_owner_secret(tmp_path):
    provider = Provider()
    state = tmp_path / "state.json"
    result = run(provider, state, apply=True)
    assert result["status"] == "deployed_requires_owner_configuration"
    assert not result["owner_password_configured"]
    assert not result["scheduled_execution_verified"] and result["renewal_schedule_installed"]
    assert not result["authorization_complete"] and not result["live_publishing"]
    original_secrets = {binding["name"]: binding["text"] for binding in provider.bindings if binding["type"] == "secret_text"}
    assert len(original_secrets["TOKEN_ENCRYPTION_KEY"]) == 43
    assert len(original_secrets["WHOP_BROKER_API_TOKEN"]) >= 32
    state_text = state.read_text()
    rendered = json.dumps(result)
    assert TOKEN not in state_text + rendered
    assert all(value not in state_text + rendered for value in original_secrets.values())
    assert set(json.loads(state_text)) == {"account_id", "worker_name", "origin", "database_id", "phase"}
    provider.bindings.append({"name": "OWNER_PASSWORD", "type": "secret_text", "text": "owner-private"})
    second = run(provider, state, apply=True, WHOP_CLIENT_ID="app_owner")
    new_secrets = {binding["name"]: binding["text"] for binding in provider.bindings if binding["type"] == "secret_text"}
    assert original_secrets.items() <= new_secrets.items()
    assert new_secrets["OWNER_PASSWORD"] == "owner-private"
    assert second["owner_password_configured"] and second["client_id_configured"]
    assert not any(binding["type"] == "secret_text" for binding in provider.uploads[-1]["bindings"])
    assert len([request for request in provider.requests if request.method == "POST" and request.url.path.endswith("/d1/database")]) == 1


def test_uncertain_initial_upload_is_resumed_without_replacing_encryption_key(tmp_path):
    provider = Provider()
    provider.fail_upload = True
    state = tmp_path / "state.json"
    with pytest.raises(deploy.DeploymentBlocked, match="HTTPS request failed") as caught:
        run(provider, state, apply=True)
    assert "private" not in str(caught.value)
    original_key = next(binding["text"] for binding in provider.bindings if binding["name"] == "TOKEN_ENCRYPTION_KEY")
    provider.fail_upload = False
    run(provider, state, apply=True)
    assert original_key == next(binding["text"] for binding in provider.bindings if binding["name"] == "TOKEN_ENCRYPTION_KEY")
    assert len(provider.databases) == 1


@pytest.mark.parametrize("resource", ["worker", "database"])
def test_existing_named_resources_without_ownership_evidence_are_not_overwritten(tmp_path, resource):
    provider = Provider()
    if resource == "worker":
        provider.bindings = []
    else:
        provider.databases = [{"uuid": DATABASE, "name": deploy.DATABASE_NAME}]
    with pytest.raises(deploy.DeploymentBlocked, match="deployment evidence"):
        run(provider, tmp_path / "state.json", apply=True)
    assert all(request.method == "GET" for request in provider.requests)


def test_deleted_deployed_worker_never_gets_a_replacement_encryption_key(tmp_path):
    provider = Provider()
    state = tmp_path / "state.json"
    run(provider, state, apply=True)
    provider.requests = []
    provider.bindings = None
    with pytest.raises(deploy.DeploymentBlocked, match="restore its encryption secret"):
        run(provider, state, apply=True)
    assert all(request.method == "GET" for request in provider.requests)


def test_interrupted_initial_deployment_with_private_rows_requires_key_recovery(tmp_path):
    provider = Provider()
    provider.databases = [{"uuid": DATABASE, "name": deploy.DATABASE_NAME}]
    provider.private_rows = 1
    state = tmp_path / "state.json"
    deploy._save_state(state, {"account_id": ACCOUNT, "worker_name": deploy.WORKER_NAME,
                              "origin": ORIGIN, "database_id": DATABASE, "phase": "database_ready"})
    with pytest.raises(deploy.DeploymentBlocked, match="restore its encryption secret"):
        run(provider, state, apply=True)
    assert provider.uploads == []


def test_schedule_and_binding_readback_must_confirm_deployment(tmp_path):
    provider = Provider()
    provider.fail_schedule_verification = True
    state = tmp_path / "state.json"
    with pytest.raises(deploy.DeploymentBlocked, match="did not confirm"):
        run(provider, state, apply=True)
    assert json.loads(state.read_text())["phase"] == "uploaded"


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_upstream_failures_never_echo_error_body_or_follow_redirect(status, tmp_path):
    calls = []
    def failed(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://untrusted.example.com"},
                              json={"success": False, "errors": [{"message": "private-provider-error"}]})
    with httpx.Client(transport=httpx.MockTransport(failed)) as client:
        with pytest.raises(deploy.DeploymentBlocked) as caught:
            deploy.deploy({"CLOUDFLARE_API_TOKEN": TOKEN}, apply=True, client=client, state_path=tmp_path / "state.json")
    assert "private" not in str(caught.value)
    assert len(calls) == 1


def test_database_binding_missing_or_altered_blocks_redeployment(tmp_path):
    provider = Provider()
    state = tmp_path / "state.json"
    run(provider, state, apply=True)
    provider.bindings = [binding for binding in provider.bindings if binding["name"] != "DB"]
    provider.requests = []
    with pytest.raises(deploy.DeploymentBlocked, match="database binding changed"):
        run(provider, state, apply=True)
    assert all(request.method == "GET" for request in provider.requests)


def test_deployed_schema_is_additive_and_preserves_existing_encrypted_records():
    schema = (SCRIPT.parents[1] / "cloud/whop/migrations/0001_owner_oauth.sql").read_text()
    with sqlite3.connect(":memory:") as database:
        database.executescript(schema)
        database.execute("UPDATE whop_credentials SET encrypted_payload=?,status='ready',version=3 WHERE owner='owner'",
                         ("encrypted-token-fixture",))
        database.executescript(schema)
        assert database.execute("SELECT encrypted_payload,status,version FROM whop_credentials").fetchone() == (
            "encrypted-token-fixture", "ready", 3)
