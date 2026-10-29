"""Authenticated operator API. Bind to loopback unless deployed behind HTTPS."""
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .integrations import IntegrationError
from .models import Campaign
from .service import Blocked, Workflow


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str
    platform: Literal["youtube", "instagram"]
    source_path: str
    title: str = Field(min_length=1, max_length=100)
    caption: str = Field(default="", max_length=2200)


class WhopDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: Literal["JO"] = "JO"
    goal: Literal["clipping", "ugc_content", "both"] = "both"
    max_pages: int = Field(default=5, ge=1, le=20)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    workflow = Workflow(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="Content Rewards", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.workflow = workflow

    def authenticate(authorization: Annotated[str | None, Header()] = None):
        if not config.admin_token:
            raise HTTPException(503, "Configure REWARDS_ADMIN_TOKEN to enable the operator API")
        expected = "Bearer " + config.admin_token
        if not authorization or not secrets.compare_digest(authorization, expected):
            raise HTTPException(401, "Bearer authentication required")

    protected = [Depends(authenticate)]

    @app.exception_handler(Blocked)
    async def blocked_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def not_found_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Record not found"})

    @app.exception_handler(ValueError)
    async def invalid_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": "Invalid operation or input"})

    @app.exception_handler(IntegrationError)
    async def integration_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"detail": "Provider operation blocked; verify secure authorization and permitted access"})

    @app.get("/health")
    def health():
        # Exercise database access, without revealing runtime bindings.
        with workflow.store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.get("/status", dependencies=protected)
    def status():
        return {"capabilities": config.credential_status(), "campaigns": len(workflow.store.list("campaign")),
                "jobs": len(workflow.store.list("job")), "automatic_spending_usd": 0}

    @app.post("/campaigns", dependencies=protected)
    def import_campaigns(campaigns: list[Campaign]):
        return {"imported": workflow.import_campaigns([c.model_dump(mode="json") for c in campaigns])}

    @app.get("/rankings", dependencies=protected)
    def rankings(platform: Literal["youtube", "instagram"] | None = None):
        return workflow.rank(platform)

    @app.get("/whop/status", dependencies=protected)
    async def whop_status():
        from .whop_broker import broker_status
        return await broker_status(config)

    @app.post("/whop/discover", dependencies=protected)
    async def whop_discover(request: WhopDiscoveryRequest):
        goals = ("clipping", "ugc_content") if request.goal == "both" else (request.goal,)
        return {"fixed_bounty_reports": [await workflow.discover_whop(request.country, goal, request.max_pages)
                                          for goal in goals],
                "cpm_campaigns": {"status": "no_verified_permitted_cpm_source", "campaigns": []},
                "live_publication_performed": False}

    @app.get("/readiness", dependencies=protected)
    def readiness_report():
        from .readiness import readiness
        return readiness(workflow)

    @app.post("/accounts/verify", dependencies=protected)
    async def verify_account_identities():
        from .readiness import verify_accounts
        return await verify_accounts(workflow)

    @app.get("/jobs", dependencies=protected)
    def jobs():
        return workflow.store.list("job")

    @app.post("/jobs", dependencies=protected)
    def plan(request: PlanRequest):
        return workflow.plan(request.campaign_id, request.platform, Path(request.source_path), request.title, request.caption)

    @app.post("/jobs/{job_id}/render", dependencies=protected)
    def render(job_id: str):
        return workflow.render(job_id)

    @app.post("/jobs/{job_id}/publish", dependencies=protected)
    async def publish(job_id: str):
        # Approval deliberately comes from an explicit local operator review.
        return await workflow.publish(job_id)

    @app.get("/jobs/{job_id}/preflight", dependencies=protected)
    def preflight_report(job_id: str):
        from .readiness import preflight
        return preflight(workflow, job_id)

    @app.post("/jobs/{job_id}/metrics", dependencies=protected)
    async def metrics(job_id: str):
        return await workflow.collect_metrics(job_id)

    @app.get("/submissions", dependencies=protected)
    def submissions():
        return workflow.store.list("submission")

    return app
