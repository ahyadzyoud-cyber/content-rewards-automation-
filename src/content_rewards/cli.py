"""Local operator commands; no paid services or publication enabled implicitly."""
import argparse
import asyncio
import json
import signal
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .config import Settings
from .integrations import IntegrationError
from .service import Blocked, Workflow


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="rewards")
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("readiness")
    sub.add_parser("verify-accounts")
    check = sub.add_parser("preflight")
    check.add_argument("job_id")
    imp = sub.add_parser("import-campaigns")
    imp.add_argument("file", type=Path)
    rank = sub.add_parser("rank")
    rank.add_argument("--platform", choices=["youtube", "instagram"])
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--platform", required=True, choices=["youtube", "instagram"])
    plan = sub.add_parser("plan")
    plan.add_argument("campaign_id")
    plan.add_argument("--platform", required=True, choices=["youtube", "instagram"])
    plan.add_argument("--source", required=True, type=Path)
    plan.add_argument("--title", required=True)
    plan.add_argument("--caption", default="")
    render = sub.add_parser("render")
    render.add_argument("job_id")
    render.add_argument("--duration", type=float, default=30)
    approve = sub.add_parser("approve")
    approve.add_argument("job_id")
    approve.add_argument("--reason", required=True, help="Record your review of eligibility, video, claims, rights and campaign requirements")
    approve.add_argument("--video-url", help="Instagram only: public HTTPS URL serving the approved MP4")
    for name in ("publish", "metrics"):
        cmd = sub.add_parser(name)
        cmd.add_argument("job_id")
    listing = sub.add_parser("list")
    listing.add_argument("kind", choices=["campaign", "job", "metrics", "submission", "report", "feed"])
    feed = sub.add_parser("add-feed")
    feed.add_argument("id")
    feed.add_argument("url")
    feed.add_argument("--confirm-permitted-no-cost", action="store_true", required=True)
    sub.add_parser("discover")
    whop = sub.add_parser("discover-whop")
    whop.add_argument("--country", default="JO")
    whop.add_argument("--goal", choices=["clipping", "ugc_content"], default="clipping")
    whop.add_argument("--max-pages", type=int, default=5)
    sub.add_parser("schedules")
    cancel = sub.add_parser("cancel-schedule")
    cancel.add_argument("id")
    submit = sub.add_parser("record-submission")
    submit.add_argument("job_id")
    submit.add_argument("--status", required=True, choices=["prepared", "submitted", "approved", "rejected", "paid"])
    submit.add_argument("--evidence-url", required=True)
    submit.add_argument("--earnings-usd", type=float, default=0)
    schedule = sub.add_parser("schedule")
    schedule.add_argument("id")
    schedule.add_argument("--action", required=True, choices=["rank", "discover", "prepare", "metrics", "publish"])
    schedule.add_argument("--interval", type=int, default=3600)
    schedule.add_argument("--job-id")
    schedule.add_argument("--platform", choices=["youtube", "instagram"])
    worker = sub.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    sub.add_parser("serve")
    return cli


async def run_worker(workflow: Workflow, once: bool = False):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    while True:
        results = await workflow.tick()
        if results and not once:
            print(json.dumps(results), flush=True)
        if once:
            return results
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
            return results
        except TimeoutError:
            pass


def execute(args, workflow: Workflow):
    match args.command:
        case "init":
            workflow.settings.media_root.mkdir(parents=True, exist_ok=True)
            workflow.store.schedule("hourly-ranking", "rank", 3600, {}, time.time())
            return {"status": "initialized", "live_publishing": workflow.settings.live_publishing}
        case "status":
            return {"capabilities": workflow.settings.credential_status(), "automatic_spending_usd": 0,
                    "campaigns": len(workflow.store.list("campaign")), "jobs": len(workflow.store.list("job"))}
        case "readiness":
            from .readiness import readiness
            return readiness(workflow)
        case "verify-accounts":
            from .readiness import verify_accounts
            return asyncio.run(verify_accounts(workflow))
        case "preflight":
            from .readiness import preflight
            return preflight(workflow, args.job_id)
        case "import-campaigns":
            records = json.loads(args.file.read_text())
            if not isinstance(records, list):
                raise ValueError("Import must be a JSON list")
            return {"imported": workflow.import_campaigns(records)}
        case "rank":
            return workflow.rank(args.platform)
        case "prepare":
            return workflow.prepare_best(args.platform)
        case "plan":
            return workflow.plan(args.campaign_id, args.platform, args.source, args.title, args.caption)
        case "render":
            return workflow.render(args.job_id, args.duration)
        case "approve":
            return workflow.approve(args.job_id, args.reason, video_url=args.video_url)
        case "publish":
            return asyncio.run(workflow.publish(args.job_id))
        case "metrics":
            return asyncio.run(workflow.collect_metrics(args.job_id))
        case "list":
            return workflow.store.list(args.kind)
        case "add-feed":
            from .feeds import validate_feed_url
            host = urlsplit(args.url).hostname
            validate_feed_url(args.url, host)
            record = {"id": args.id, "url": args.url, "allowed_host": host, "no_cost_confirmed": True}
            workflow.store.put("feed", args.id, record)
            return record
        case "discover":
            return asyncio.run(workflow.discover())
        case "discover-whop":
            return asyncio.run(workflow.discover_whop(args.country, args.goal, args.max_pages))
        case "schedules":
            return workflow.store.schedules()
        case "cancel-schedule":
            workflow.store.cancel_schedule(args.id)
            return {"cancelled": args.id}
        case "record-submission":
            return workflow.record_submission(args.job_id, args.status, args.evidence_url, args.earnings_usd)
        case "schedule":
            if args.action in {"metrics", "publish"} and not args.job_id:
                raise ValueError("This schedule requires --job-id")
            if args.action == "prepare" and not args.platform:
                raise ValueError("Prepare schedule requires --platform")
            workflow.store.schedule(args.id, args.action, args.interval,
                                    {"job_id": args.job_id, "platform": args.platform}, time.time())
            return {"scheduled": args.id}
        case "worker":
            workflow.store.schedule("hourly-ranking", "rank", 3600, {}, time.time())
            return asyncio.run(run_worker(workflow, args.once))
        case "serve":
            import uvicorn
            uvicorn.run("content_rewards.api:create_app", factory=True, host="127.0.0.1", port=8000)


def main():
    args = parser().parse_args()
    try:
        result = execute(args, Workflow(Settings()))
        if result is not None:
            print(json.dumps(result, indent=2))
    except (Blocked, ValueError, KeyError, FileNotFoundError) as exc:
        # Do not print arbitrary exception messages that may embed credentialed upstream URLs.
        message = str(exc) if isinstance(exc, Blocked) else f"{type(exc).__name__}: invalid input or missing record/file"
        print(json.dumps({"error": message}), file=sys.stderr)
        raise SystemExit(1) from None
    except (IntegrationError, httpx.HTTPError, OSError):
        print(json.dumps({"error": "Integration or local I/O failed; check authorization, connectivity and configured paths"}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
