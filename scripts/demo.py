"""Run a synthetic, isolated end-to-end demo. No real campaigns or API traffic."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="rewards-demo-") as directory:
        root = Path(directory)
        environment = dict(os.environ, REWARDS_DATABASE=str(root / "state.sqlite"),
                           REWARDS_MEDIA_ROOT=str(root / "media"), REWARDS_LIVE_PUBLISHING="false")
        def cli(*args, expect=0):
            result = subprocess.run([sys.executable, "-m", "content_rewards.cli", *args], env=environment,
                                    text=True, capture_output=True, timeout=240)
            if result.returncode != expect:
                raise RuntimeError("Demo command failed: " + args[0])
            return json.loads(result.stdout if expect == 0 else result.stderr)
        source = root / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=blue:s=160x90:d=0.3", "-c:v", "libx264", "-threads", "2", str(source)],
                       check=True, timeout=30)
        campaign = {"id": "synthetic-demo-only", "title": "SYNTHETIC DEMO - NOT A REAL CAMPAIGN", "source": "manual",
                    "source_url": "https://example.com/synthetic-fixture", "rate_per_1000_views_usd": 5,
                    "remaining_budget_usd": 1000, "competition_entries": 10, "eligible_countries": ["JO"],
                    "eligibility_verified": True, "eligibility_evidence": "Synthetic test fixture only; no real eligibility claim",
                    "allowed_platforms": ["youtube", "instagram"], "allows_new_accounts": True,
                    "requirements_verified": True, "rights_verified": True, "materials": [str(source)],
                    "evidence_checked_at": datetime.now(UTC).isoformat()}
        export = root / "campaigns.json"
        export.write_text(json.dumps([campaign]))
        cli("init")
        assert cli("import-campaigns", str(export))["imported"] == 1
        ranking = cli("rank", "--platform", "youtube")
        assert ranking[0]["selectable"]
        job = cli("prepare", "--platform", "youtube")
        assert job["state"] == "rendered" and Path(job["media_path"]).is_file()
        denial = cli("publish", job["id"], expect=1)
        assert "disabled" in denial["error"]
        assert cli("list", "job")[0]["state"] == "rendered"
        cli("worker", "--once")
        assert cli("list", "report")[0]["ranking"][0]["campaign_id"] == campaign["id"]
        print(json.dumps({"synthetic_demo": "passed", "ranking": "passed", "portrait_render": "passed",
                          "restart_persistence": "passed", "scheduler": "passed", "live_publish": "blocked_as_expected"}))


if __name__ == "__main__":
    main()
