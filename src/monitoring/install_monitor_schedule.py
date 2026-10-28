
"""
INNEVA.E - HEALTH MONITOR SCHEDULER
Checkpoint 15.9E

Installs a macOS launchd configuration for
daily automation health checks at 10:00.

No notifications.
No Ollama calls.
No changes to the weekly report scheduler.
"""

import plistlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PYTHON_PATH = PROJECT_ROOT / ".venv/bin/python3"

MONITOR_SCRIPT = (
    PROJECT_ROOT
    / "src/monitoring/automation_health_monitor.py"
)

LOG_DIRECTORY = (
    PROJECT_ROOT / "logs/monitoring"
)

PLIST_PATH = (
    Path.home()
    / "Library/LaunchAgents/com.innevae.health-monitor.plist"
)


def main():

    if not PYTHON_PATH.is_file():
        raise FileNotFoundError(PYTHON_PATH)

    if not MONITOR_SCRIPT.is_file():
        raise FileNotFoundError(MONITOR_SCRIPT)

    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    PLIST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    configuration = {
        "Label": "com.innevae.health-monitor",

        "ProgramArguments": [
            str(PYTHON_PATH),
            str(MONITOR_SCRIPT),
        ],

        "WorkingDirectory": str(PROJECT_ROOT),

        "StartCalendarInterval": {
            "Hour": 10,
            "Minute": 0,
        },

        "RunAtLoad": False,

        "ProcessType": "Background",

        "StandardOutPath": str(
            LOG_DIRECTORY / "health_stdout.log"
        ),

        "StandardErrorPath": str(
            LOG_DIRECTORY / "health_stderr.log"
        ),

        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
    }

    with PLIST_PATH.open("wb") as file:
        plistlib.dump(configuration, file)

    print("Health monitoring schedule created.")
    print(f"Configuration: {PLIST_PATH}")
    print("Schedule: Every day at 10:00 local time.")
    print("Notifications: Disabled.")


if __name__ == "__main__":
    main()
