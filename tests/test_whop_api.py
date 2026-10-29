from fastapi.testclient import TestClient

from content_rewards.api import create_app
from content_rewards.config import Settings
from content_rewards.integrations import IntegrationError


def configured_app(tmp_path):
    return create_app(Settings(database=tmp_path / "operator.sqlite", admin_token="private-owner",
                               whop_token="", whop_broker_url="", whop_broker_token="", live_publishing=False))


def test_whop_endpoints_require_owner_and_do_not_expose_oauth_callback(tmp_path):
    with TestClient(configured_app(tmp_path)) as client:
        assert client.get("/whop/status").status_code == 401
        assert client.post("/whop/discover", json={}).status_code == 401
        # Production callback lives only on the separate secure HTTPS broker.
        assert client.get("/oauth/callback?code=private-code").status_code == 404


def test_missing_grant_is_explicit_and_live_stays_disabled(tmp_path):
    app = configured_app(tmp_path)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer private-owner"}
        response = client.get("/whop/status", headers=headers)
        assert response.json()["requested_scope"] == "bounty:basic:read"
        assert response.json()["live_publishing"] is False
        result = client.post("/whop/discover", json={}, headers=headers)
        assert result.status_code == 409
        assert "only bounty:basic" in result.json()["detail"]
        assert not app.state.workflow.store.list("job")


def test_authenticated_discovery_runs_both_goals_and_separates_cpm(tmp_path, monkeypatch):
    app = configured_app(tmp_path)
    goals = []
    async def discover(country, goal, max_pages):
        assert country == "JO" and max_pages == 2
        goals.append(goal)
        return {"pricing_model": "fixed_reward_per_approved_submission", "business_goal_type": goal,
                "rankings": [], "eligible_campaigns_verified": False}
    monkeypatch.setattr(app.state.workflow, "discover_whop", discover)
    with TestClient(app) as client:
        result = client.post("/whop/discover", json={"max_pages": 2}, headers={"Authorization": "Bearer private-owner"})
    assert result.status_code == 200
    assert goals == ["clipping", "ugc_content"]
    assert result.json()["cpm_campaigns"] == {"status": "no_verified_permitted_cpm_source", "campaigns": []}
    assert result.json()["live_publication_performed"] is False


def test_provider_error_does_not_echo_secrets(tmp_path, monkeypatch):
    app = configured_app(tmp_path)
    async def failed(*args):
        raise IntegrationError("private-token-in-upstream-error")
    monkeypatch.setattr(app.state.workflow, "discover_whop", failed)
    with TestClient(app) as client:
        response = client.post("/whop/discover", json={}, headers={"Authorization": "Bearer private-owner"})
    assert response.status_code == 502
    assert "private" not in response.text
