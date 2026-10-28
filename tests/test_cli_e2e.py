"""Exercise installed commands and a real FFmpeg render across separate processes."""
import json
import subprocess
import sys
from pathlib import Path


def test_isolated_synthetic_workflow():
    demo = Path(__file__).resolve().parents[1] / "scripts/demo.py"
    result = subprocess.run([sys.executable, str(demo)], capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == {"synthetic_demo": "passed", "ranking": "passed", "portrait_render": "passed",
                      "restart_persistence": "passed", "scheduler": "passed", "live_publish": "blocked_as_expected"}
