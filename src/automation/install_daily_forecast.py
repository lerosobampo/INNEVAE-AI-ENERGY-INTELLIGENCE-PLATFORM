"""Install the development-only 07:15 local-time macOS LaunchAgent.

Never modifies any existing INNEVA.E LaunchAgent.
"""
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABEL = "com.innevae.daily-forecast"
AGENT = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOGS = ROOT / "reports" / "forecast_automation"
SCRIPT = ROOT / "src" / "automation" / "forecast_post_refresh.py"
PYTHON = ROOT / ".venv" / "bin" / "python3"


def main():
    if not PYTHON.is_file() or not SCRIPT.is_file():
        raise FileNotFoundError("Missing virtualenv Python or forecast_post_refresh.py")
    if AGENT.exists():
        raise FileExistsError(f"Agent already exists; refusing overwrite: {AGENT}")
    LOGS.mkdir(parents=True, exist_ok=True)
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProcessType": "Background",
        "ProgramArguments": [str(PYTHON), str(SCRIPT), "run"],
        "RunAtLoad": False,
        "StartCalendarInterval": {"Hour": 7, "Minute": 15},
        "WorkingDirectory": str(ROOT),
        "StandardOutPath": str(LOGS / "daily_forecast_stdout.log"),
        "StandardErrorPath": str(LOGS / "daily_forecast_stderr.log"),
    }
    with AGENT.open("wb") as handle:
        plistlib.dump(config, handle)
    uid = subprocess.check_output(["id", "-u"], text=True).strip()
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(AGENT)], check=True)
    print(f"INSTALLED: {LABEL}")
    print(f"PLIST: {AGENT}")
    print("SCHEDULE: 07:15 local macOS time")
    print("Existing agents: unchanged")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"INSTALL_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
