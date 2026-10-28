"""Operator API boundaries; all media and provider activity is local/faked."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from content_rewards.api import create_app
from content_rewards.config import Settings


@pytest.fixture
def operator(tmp_path, monkeypatch):
    settings = Settings(
        database=tmp_path / "api.sqlite", media_root=tmp_path / "media",
        admin_token="test-admin-sensitive", youtube_token="test-youtube-sensitive",
        youtube_channel_id="channel1", instagram_token="test-instagram-sensitive",
        instagram_account_id="account1", instagram_api_version="v24.0",
        live_publishing=False,
    )

    def fake_render(source, output, **kwargs):
        assert Path(source).read_bytes() == b"approved-source"
        assert kwargs["rights_verified"] is True
        Path(output).write_bytes(b"rendered-api-mp4")

    monkeypatch.setattr("content_rewards.service.render_short", fake_render)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app.state.workflow, {"Authorization": "Bearer " + settings.admin_token}


def campaign(tmp_path, **changes):
    source = tmp_path / "approved-api-source.mp4"
    source.write_bytes(b"approved-source")
    return {
        "id": "api-campaign", "title": "Operator verified test campaign",
        "source": "manual", "source_url": "https://example.com/campaign",
        "rate_per_1000_views_usd": 4, "remaining_budget_usd": 500,
        "competition_entries": 5, "eligible_countries": ["JO"],
        "eligibility_verified": True, "eligibility_evidence": "Verified fixture terms allow Jordan",
        "allowed_platforms": ["youtube", "instagram"], "allows_new_accounts": True,
        "requirements_verified": True, "rights_verified": True, "materials": [str(source)],
        "evidence_checked_at": datetime.now(UTC).isoformat(),
    } | changes


def test_health_checks_storage_and_status_never_discloses_configured_secrets(operator):
    client, _, headers = operator
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/status", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "capabilities": {"youtube": True, "instagram": True, "api_auth": True, "live_publishing": False},
        "campaigns": 0, "jobs": 0, "automatic_spending_usd": 0,
    }
    assert "sensitive" not in response.text
    assert "channel1" not in response.text
    assert "account1" not in response.text


@pytest.mark.parametrize("authorization", [None, "test-admin-sensitive", "Bearer wrong", "bearer test-admin-sensitive"])
def test_operator_routes_reject_missing_or_invalid_bearer_tokens(operator, authorization):
    client, _, _ = operator
    headers = {"Authorization": authorization} if authorization else {}
    for path in ("/status", "/jobs", "/rankings", "/submissions"):
        response = client.get(path, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": "Bearer authentication required"}
        assert "sensitive" not in response.text
    assert client.post("/campaigns", json=[], headers=headers).status_code == 401


def test_no_admin_token_disables_operator_api_without_disabling_health(tmp_path):
    app = create_app(Settings(database=tmp_path / "empty.sqlite", admin_token=""))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/status")
        assert response.status_code == 503
        assert "REWARDS_ADMIN_TOKEN" in response.json()["detail"]


def test_authenticated_import_rank_plan_and_render_flow(operator, tmp_path, monkeypatch):
    client, workflow, headers = operator
    record = campaign(tmp_path)
    response = client.post("/campaigns", json=[record], headers=headers)
    assert response.status_code == 200
    assert response.json() == {"imported": 1}
    rankings = client.get("/rankings?platform=youtube", headers=headers).json()
    assert rankings[0]["campaign_id"] == record["id"]
    assert rankings[0]["selectable"] is True
    assert 0 <= rankings[0]["score"] <= 10
    response = client.post("/jobs", json={
        "campaign_id": record["id"], "platform": "youtube", "source_path": record["materials"][0],
        "title": "Reviewed title", "caption": "Campaign disclosure",
    }, headers=headers)
    assert response.status_code == 200
    job = response.json()
    assert job["state"] == "planned"
    response = client.post(f"/jobs/{job['id']}/render", headers=headers)
    assert response.status_code == 200
    assert response.json()["state"] == "rendered"
    assert Path(response.json()["media_path"]).read_bytes() == b"rendered-api-mp4"
    assert client.get("/jobs", headers=headers).json()[0]["id"] == job["id"]

    async def unexpected(*args, **kwargs):
        pytest.fail("Disabled publishing must fail before creating a provider client")

    monkeypatch.setattr(workflow, "_publisher", unexpected)
    response = client.post(f"/jobs/{job['id']}/publish", headers=headers)
    assert response.status_code == 409
    assert "disabled" in response.json()["detail"]
    assert workflow.store.get("job", job["id"])["state"] == "rendered"
    assert client.post(f"/jobs/{job['id']}/metrics", headers=headers).status_code == 409


def test_api_cannot_self_approve_or_expose_approval_through_openapi(operator):
    client, _, headers = operator
    assert client.post("/jobs/example/approve", json={"reason": "remote approval"}, headers=headers).status_code == 404
    assert client.get("/docs", headers=headers).status_code == 404
    assert client.get("/openapi.json", headers=headers).status_code == 404


def test_unverified_campaign_is_importable_but_cannot_plan(operator, tmp_path):
    client, workflow, headers = operator
    record = campaign(tmp_path, eligibility_verified=False, rights_verified=False)
    assert client.post("/campaigns", json=[record], headers=headers).status_code == 200
    assert client.get("/rankings", headers=headers).json()[0]["selectable"] is False
    response = client.post("/jobs", json={
        "campaign_id": record["id"], "platform": "youtube", "source_path": record["materials"][0], "title": "Title",
    }, headers=headers)
    assert response.status_code == 409
    assert workflow.store.list("job") == []


def test_api_rejects_invalid_batch_and_extra_plan_fields(operator, tmp_path):
    client, workflow, headers = operator
    record = campaign(tmp_path)
    response = client.post("/campaigns", json=[record, record | {"id": "bad", "remaining_budget_usd": -1}], headers=headers)
    assert response.status_code == 422
    assert workflow.store.list("campaign") == []
    response = client.post("/jobs", json={
        "campaign_id": "api-campaign", "platform": "youtube", "source_path": "/unapproved.mp4",
        "title": "Title", "approval": {"digest": "forged"},
    }, headers=headers)
    assert response.status_code == 422
    assert workflow.store.list("job") == []


def test_missing_records_return_sanitized_not_found(operator):
    client, _, headers = operator
    response = client.post("/jobs/unknown-record/render", headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Record not found"}
