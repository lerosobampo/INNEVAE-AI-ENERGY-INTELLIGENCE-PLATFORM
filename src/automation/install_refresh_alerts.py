
"""INNEVA.E — Checkpoint 20.5C.3D.

Install and manage the independent macOS refresh-alert
LaunchAgent.

Schedule: 08:15 local time, daily.

Does not modify the existing daily refresh, weekly
automation, production dataset, or ingestion history.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

RUNNER = (
    ROOT / "src" / "automation"
    / "refresh_alerts.py"
)

LABEL = "com.innevae.refresh-alerts"

AGENTS_DIR = (
    Path.home() / "Library" / "LaunchAgents"
)

PLIST_PATH = AGENTS_DIR / f"{LABEL}.plist"

LOG_DIR = (
    ROOT / "reports" / "data_quality"
    / "refresh_alerts"
)

STDOUT_LOG = LOG_DIR / "launchd_stdout.log"
STDERR_LOG = LOG_DIR / "launchd_stderr.log"

DOMAIN = f"gui/{os.getuid()}"
SERVICE = f"{DOMAIN}/{LABEL}"

HOUR = 8
MINUTE = 15


def command(arguments: list[str]):
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        check=False,
    )


def build_plist():
    return {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            str(RUNNER),
            "check",
        ],
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {
            "Hour": HOUR,
            "Minute": MINUTE,
        },
        "RunAtLoad": False,
        "StandardOutPath": str(STDOUT_LOG),
        "StandardErrorPath": str(STDERR_LOG),
    }


def service_status():
    installed = PLIST_PATH.is_file()

    result = command([
        "launchctl",
        "print",
        SERVICE,
    ])

    loaded = result.returncode == 0

    configuration = None
    configuration_error = None

    if installed:
        try:
            with PLIST_PATH.open("rb") as handle:
                configuration = plistlib.load(handle)

        except (
            OSError,
            ValueError,
            TypeError,
        ) as error:
            configuration_error = str(error)

    arguments = (
        configuration.get("ProgramArguments", [])
        if isinstance(configuration, dict)
        else []
    )

    schedule = (
        configuration.get("StartCalendarInterval")
        if isinstance(configuration, dict)
        else None
    )

    return {
        "installed": installed,
        "loaded": loaded,
        "label": LABEL,
        "service": SERVICE,
        "plist_path": str(PLIST_PATH),
        "schedule": schedule,
        "program_arguments": arguments,
        "run_at_load": (
            configuration.get("RunAtLoad")
            if isinstance(configuration, dict)
            else None
        ),
        "configuration_error": configuration_error,
        "launchctl_output": (
            result.stdout.strip()
            if loaded
            else result.stderr.strip()
        ),
    }


def install():
    if sys.platform != "darwin":
        return {
            "status": "ERROR",
            "reason": "macOS is required",
        }

    if not RUNNER.is_file():
        return {
            "status": "ERROR",
            "reason": (
                "Alert runner not found: "
                f"{RUNNER}"
            ),
        }

    if PLIST_PATH.exists():
        return {
            "status": "ALREADY_INSTALLED",
            "reason": (
                "Existing plist was not overwritten"
            ),
            "details": service_status(),
        }

    AGENTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    configuration = build_plist()

    temporary = PLIST_PATH.with_suffix(
        ".plist.tmp"
    )

    try:
        with temporary.open("wb") as handle:
            plistlib.dump(
                configuration,
                handle,
            )

        validation = command([
            "plutil",
            "-lint",
            str(temporary),
        ])

        if validation.returncode != 0:
            return {
                "status": "ERROR",
                "reason": "Invalid plist",
                "details": validation.stderr.strip(),
            }

        temporary.replace(PLIST_PATH)

        bootstrap = command([
            "launchctl",
            "bootstrap",
            DOMAIN,
            str(PLIST_PATH),
        ])

        if bootstrap.returncode != 0:
            # Preserve the plist for inspection.
            return {
                "status": "ERROR",
                "reason": "LaunchAgent bootstrap failed",
                "details": bootstrap.stderr.strip(),
                "plist_path": str(PLIST_PATH),
            }

        return {
            "status": "INSTALLED",
            "label": LABEL,
            "schedule": "08:15 local time",
            "service": SERVICE,
            "run_at_load": False,
            "existing_automations_modified": False,
        }

    except OSError as error:
        return {
            "status": "ERROR",
            "reason": str(error),
        }

    finally:
        if temporary.exists():
            temporary.unlink()


def uninstall():
    if not PLIST_PATH.exists():
        return {
            "status": "NOT_INSTALLED",
            "label": LABEL,
        }

    status = service_status()

    if status["loaded"]:
        result = command([
            "launchctl",
            "bootout",
            SERVICE,
        ])

        if result.returncode != 0:
            return {
                "status": "ERROR",
                "reason": "Could not unload service",
                "details": result.stderr.strip(),
            }

    try:
        PLIST_PATH.unlink()

    except OSError as error:
        return {
            "status": "ERROR",
            "reason": str(error),
        }

    return {
        "status": "UNINSTALLED",
        "label": LABEL,
        "existing_automations_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="INNEVA.E refresh alert scheduler"
    )

    parser.add_argument(
        "action",
        choices=[
            "install",
            "status",
            "uninstall",
        ],
    )

    args = parser.parse_args()

    if args.action == "install":
        result = install()

    elif args.action == "uninstall":
        result = uninstall()

    else:
        result = service_status()

    print(json.dumps(
        result,
        indent=2,
    ))

    return (
        1
        if result.get("status") == "ERROR"
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
