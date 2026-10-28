"""INNEVA.E checkpoint 19.7.2: stage (do not install) a weekly launchd agent.

Creates a plist inside the project for inspection. Never calls launchctl.
Schedule: Mondays 18:00, in the Mac's local timezone (must be Europe/Amsterdam).
"""
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABEL = "com.innevae.energy-intelligence.weekly"
AUTOMATION = ROOT / "src" / "automation"
JOB = AUTOMATION / "scheduled_energy_job.py"
PYTHON = ROOT / ".venv" / "bin" / "python3"
STAGING = ROOT / "reports" / "automation" / "launchd"
PLIST = STAGING / f"{LABEL}.plist"
LOG_DIR = ROOT / "reports" / "automation" / "scheduler_logs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage an inactive weekly launchd job")
    parser.add_argument("--check", action="store_true", help="Inspect staged config without modifying files")
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("ERROR: This setup is for macOS only.")
        return 2
    if not JOB.is_file() or not PYTHON.is_file():
        print(f"ERROR: Missing job or venv Python: {JOB} | {PYTHON}")
        return 2

    if not args.check:
        STAGING.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        config = {
            "Label": LABEL,
            "ProgramArguments": [str(PYTHON), str(JOB), "--run"],
            "WorkingDirectory": str(ROOT),
            "StartCalendarInterval": {"Weekday": 1, "Hour": 18, "Minute": 0},
            "RunAtLoad": False,
            "StandardOutPath": str(LOG_DIR / "weekly_stdout.log"),
            "StandardErrorPath": str(LOG_DIR / "weekly_stderr.log"),
        }
        with PLIST.open("wb") as f:
            plistlib.dump(config, f, sort_keys=True)
    if not PLIST.is_file():
        print("ERROR: No staged plist found; run without --check first.")
        return 2
    with PLIST.open("rb") as f:
        data = plistlib.load(f)
    expected = {"Weekday": 1, "Hour": 18, "Minute": 0}
    assert data["StartCalendarInterval"] == expected, "Schedule mismatch"
    assert data["RunAtLoad"] is False, "Unexpected RunAtLoad"
    assert data["ProgramArguments"] == [str(PYTHON), str(JOB), "--run"], "Command mismatch"
    assert data["WorkingDirectory"] == str(ROOT), "Working directory mismatch"
    checked = subprocess.run(["plutil", "-lint", str(PLIST)], text=True, capture_output=True)
    if checked.returncode:
        print("ERROR: plutil rejected the plist:", checked.stdout, checked.stderr)
        return 3
    print("STATUS: STAGED_ONLY_NOT_INSTALLED")
    print("SCHEDULE: Monday 18:00 Mac local time (verify Europe/Amsterdam)")
    print(f"PLIST: {PLIST}")
    print(f"COMMAND: {PYTHON} {JOB} --run")
    print(f"LOGS: {LOG_DIR}")
    print("PLUTIL: OK")
    print("ENABLED: NO (no launchctl command was executed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
