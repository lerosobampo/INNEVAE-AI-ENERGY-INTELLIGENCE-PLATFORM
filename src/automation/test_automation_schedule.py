
"""INNEVA.E — Accelerated launchd scheduling test.

Temporarily schedules the daily refresh and alert check
within the next 10 minutes.

Restores the original LaunchAgent configurations even
if the test fails or is interrupted normally.

Does not change production data or execution history.
The normal refresh and alert runners still record their
real executions.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]

TIMEZONE = ZoneInfo("Europe/Amsterdam")

AGENTS = Path.home() / "Library" / "LaunchAgents"

SERVICES = {
    "refresh": "com.innevae.daily-data-refresh",
    "alerts": "com.innevae.refresh-alerts",
}

DOMAIN = f"gui/{os.getuid()}"

BACKUP_DIR = (
    ROOT / "reports" / "data_quality"
    / "accelerated_schedule_test"
)

BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def run_command(arguments):
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        check=False,
    )


def service_name(label):
    return f"{DOMAIN}/{label}"


def loaded(label):
    return run_command([
        "launchctl",
        "print",
        service_name(label),
    ]).returncode == 0


def reload_service(label, plist_path):
    if loaded(label):
        result = run_command([
            "launchctl",
            "bootout",
            service_name(label),
        ])

        if result.returncode != 0:
            raise RuntimeError(
                f"Cannot unload {label}: "
                f"{result.stderr}"
            )

    result = run_command([
        "launchctl",
        "bootstrap",
        DOMAIN,
        str(plist_path),
    ])

    if result.returncode != 0:
        raise RuntimeError(
            f"Cannot load {label}: "
            f"{result.stderr}"
        )


def read_plist(path):
    with path.open("rb") as handle:
        return plistlib.load(handle)


def write_plist(path, data):
    temporary = path.with_suffix(
        ".plist.testing"
    )

    with temporary.open("wb") as handle:
        plistlib.dump(data, handle)

    temporary.replace(path)


def schedule_at(path, target):
    config = read_plist(path)

    config["StartCalendarInterval"] = {
        "Hour": target.hour,
        "Minute": target.minute,
    }

    config["RunAtLoad"] = False

    write_plist(path, config)


def test_schedule():
    if sys.platform != "darwin":
        raise RuntimeError(
            "This test requires macOS"
        )

    now = datetime.now(TIMEZONE)

    refresh_time = (
        now + timedelta(minutes=2)
    ).replace(second=0, microsecond=0)

    alert_time = (
        now + timedelta(minutes=5)
    ).replace(second=0, microsecond=0)

    paths = {
        name: AGENTS / f"{label}.plist"
        for name, label in SERVICES.items()
    }

    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(
                f"Missing {name} plist: {path}"
            )

    timestamp = now.strftime(
        "%Y%m%dT%H%M%S"
    )

    backups = {}

    # Preserve exact original plist bytes.
    for name, path in paths.items():
        backup = BACKUP_DIR / (
            f"{SERVICES[name]}.{timestamp}.plist"
        )

        backup.write_bytes(
            path.read_bytes()
        )

        backups[name] = backup

    print(json.dumps({
        "status": "TEST_STARTING",
        "refresh_target_local": (
            refresh_time.isoformat()
        ),
        "alert_target_local": (
            alert_time.isoformat()
        ),
        "backups": {
            key: str(value)
            for key, value in backups.items()
        },
    }, indent=2), flush=True)

    try:
        # Temporarily install the test schedules.
        schedule_at(
            paths["refresh"],
            refresh_time,
        )

        reload_service(
            SERVICES["refresh"],
            paths["refresh"],
        )

        schedule_at(
            paths["alerts"],
            alert_time,
        )

        reload_service(
            SERVICES["alerts"],
            paths["alerts"],
        )

        # Wait beyond both scheduled events.
        end_time = alert_time + timedelta(
            minutes=1
        )

        while datetime.now(TIMEZONE) < end_time:
            remaining = (
                end_time - datetime.now(TIMEZONE)
            ).total_seconds()

            print(
                f"Waiting for scheduled execution: "
                f"{int(max(remaining, 0))}s remaining",
                flush=True,
            )

            time.sleep(
                min(30, max(1, remaining))
            )

        print(json.dumps({
            "status": "TEST_WINDOW_FINISHED",
            "refresh_loaded": loaded(
                SERVICES["refresh"]
            ),
            "alerts_loaded": loaded(
                SERVICES["alerts"]
            ),
        }, indent=2), flush=True)

    finally:
        print(
            "Restoring original schedules...",
            flush=True,
        )

        for name, label in SERVICES.items():
            try:
                paths[name].write_bytes(
                    backups[name].read_bytes()
                )

                reload_service(
                    label,
                    paths[name],
                )

                print(
                    f"RESTORED: {label}",
                    flush=True,
                )

            except Exception as error:
                print(
                    f"RESTORE_FAILED: {label}: {error}",
                    file=sys.stderr,
                    flush=True,
                )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "action",
        choices=["run"],
    )

    parser.parse_args()

    test_schedule()


if __name__ == "__main__":
    main()
