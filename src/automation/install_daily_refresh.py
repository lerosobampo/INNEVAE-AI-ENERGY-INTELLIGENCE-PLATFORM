
"""INNEVA.E — macOS daily refresh scheduler.

Checkpoint 20.5C.3A:
- Installs the daily 07:00 LaunchAgent.
- Updates an existing LaunchAgent with backup/rollback.
- Passes --source LAUNCHD to the refresh runner.
- Preserves the weekly automation and audit history.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

RUNNER = (
    ROOT / "src" / "automation"
    / "daily_data_refresh.py"
)

LABEL = "com.innevae.daily-data-refresh"

AGENTS_DIR = (
    Path.home() / "Library" / "LaunchAgents"
)

PLIST_PATH = AGENTS_DIR / f"{LABEL}.plist"

LOG_DIR = (
    ROOT / "reports" / "data_quality"
    / "daily_refresh"
)

BACKUP_DIR = LOG_DIR / "scheduler_backups"

STDOUT_LOG = LOG_DIR / "launchd_stdout.log"
STDERR_LOG = LOG_DIR / "launchd_stderr.log"

DOMAIN = f"gui/{os.getuid()}"
SERVICE = f"{DOMAIN}/{LABEL}"

HOUR = 7
MINUTE = 0


def command(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        check=False,
    )


def is_loaded() -> bool:
    result = command(
        "launchctl",
        "print",
        SERVICE,
    )

    return result.returncode == 0


def build_plist() -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            str(RUNNER),
            "run",
            "--source",
            "LAUNCHD",
        ],
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {
            "Hour": HOUR,
            "Minute": MINUTE,
        },
        "RunAtLoad": False,
        "StandardOutPath": str(STDOUT_LOG),
        "StandardErrorPath": str(STDERR_LOG),
        "ProcessType": "Background",
    }


def validate_plist(path: Path) -> bool:
    result = command(
        "plutil",
        "-lint",
        str(path),
    )

    return result.returncode == 0


def write_plist(
    path: Path,
    content: dict,
) -> None:
    with path.open("wb") as handle:
        plistlib.dump(content, handle)


def service_status() -> dict:
    result = command(
        "launchctl",
        "print",
        SERVICE,
    )

    arguments = None

    if PLIST_PATH.is_file():
        try:
            with PLIST_PATH.open("rb") as handle:
                arguments = plistlib.load(
                    handle
                ).get("ProgramArguments")
        except (
            OSError,
            ValueError,
            plistlib.InvalidFileException,
        ):
            arguments = None

    return {
        "installed": PLIST_PATH.is_file(),
        "loaded": result.returncode == 0,
        "plist_path": str(PLIST_PATH),
        "service": SERVICE,
        "schedule": "07:00 daily",
        "program_arguments": arguments,
        "execution_source_configured": (
            isinstance(arguments, list)
            and "--source" in arguments
            and "LAUNCHD" in arguments
        ),
        "launchctl_output": (
            result.stdout.strip()
            if result.returncode == 0
            else result.stderr.strip()
        ),
    }


def install() -> int:
    if sys.platform != "darwin":
        print("ERROR: macOS required.")
        return 1

    if not RUNNER.is_file():
        print(
            f"ERROR: Runner missing: {RUNNER}"
        )
        return 1

    if PLIST_PATH.exists() or is_loaded():
        print(
            "INSTALLATION STOPPED: "
            "Daily refresh already installed. "
            "Use the update command."
        )
        return 1

    AGENTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_plist(
        PLIST_PATH,
        build_plist(),
    )

    if not validate_plist(PLIST_PATH):
        PLIST_PATH.unlink(missing_ok=True)
        print("ERROR: Invalid LaunchAgent plist.")
        return 1

    result = command(
        "launchctl",
        "bootstrap",
        DOMAIN,
        str(PLIST_PATH),
    )

    if result.returncode != 0:
        print(
            "ERROR: Could not load LaunchAgent. "
            f"{result.stderr.strip()}"
        )
        return 1

    print(json.dumps({
        "status": "INSTALLED",
        "label": LABEL,
        "schedule": "07:00 local time",
        "execution_source": "LAUNCHD",
        "weekly_automation_modified": False,
    }, indent=2))

    return 0


def update() -> int:
    if sys.platform != "darwin":
        print("ERROR: macOS required.")
        return 1

    if not RUNNER.is_file():
        print("ERROR: Runner missing.")
        return 1

    if not PLIST_PATH.is_file():
        print(
            "ERROR: No existing daily LaunchAgent. "
            "Use install instead."
        )
        return 1

    if not is_loaded():
        print(
            "ERROR: Existing daily LaunchAgent "
            "is not loaded. Resolve this before updating."
        )
        return 1

    with PLIST_PATH.open("rb") as handle:
        existing = plistlib.load(handle)

    if existing.get("Label") != LABEL:
        print(
            "ERROR: Existing plist label differs. "
            "Update cancelled."
        )
        return 1

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    backup = (
        BACKUP_DIR
        / f"{LABEL}.{timestamp}.plist"
    )

    # Preserve the exact existing plist bytes.
    backup.write_bytes(
        PLIST_PATH.read_bytes()
    )

    new_plist = build_plist()

    # Keep the installed interpreter path when
    # updating the existing service.
    previous_arguments = existing.get(
        "ProgramArguments",
        [],
    )

    if previous_arguments:
        new_plist["ProgramArguments"][0] = (
            previous_arguments[0]
        )

    # Validate a temporary plist before unloading
    # the existing working service.
    temporary = PLIST_PATH.with_suffix(
        ".plist.pending"
    )

    write_plist(
        temporary,
        new_plist,
    )

    if not validate_plist(temporary):
        temporary.unlink(missing_ok=True)
        print(
            "ERROR: New plist validation failed. "
            "Existing service unchanged."
        )
        return 1

    unloaded = command(
        "launchctl",
        "bootout",
        DOMAIN,
        str(PLIST_PATH),
    )

    if unloaded.returncode != 0:
        temporary.unlink(missing_ok=True)
        print(
            "ERROR: Could not unload existing service. "
            "No replacement performed."
        )
        return 1

    try:
        temporary.replace(PLIST_PATH)

        loaded = command(
            "launchctl",
            "bootstrap",
            DOMAIN,
            str(PLIST_PATH),
        )

        if loaded.returncode != 0:
            raise RuntimeError(
                loaded.stderr.strip()
                or "launchctl bootstrap failed"
            )

    except Exception as error:
        print(
            "UPDATE FAILED: "
            f"{type(error).__name__}: {error}"
        )

        # Restore the original plist and attempt
        # to reload the original service.
        PLIST_PATH.write_bytes(
            backup.read_bytes()
        )

        if is_loaded():
            command(
                "launchctl",
                "bootout",
                DOMAIN,
                str(PLIST_PATH),
            )

        rollback = command(
            "launchctl",
            "bootstrap",
            DOMAIN,
            str(PLIST_PATH),
        )

        print(json.dumps({
            "status": (
                "ROLLED_BACK"
                if rollback.returncode == 0
                else "ROLLBACK_REQUIRES_ATTENTION"
            ),
            "backup": str(backup),
            "rollback_error": (
                rollback.stderr.strip()
                if rollback.returncode != 0
                else None
            ),
        }, indent=2))

        return 1

    print(json.dumps({
        "status": "UPDATED",
        "label": LABEL,
        "schedule": "07:00 local time",
        "execution_source": "LAUNCHD",
        "backup": str(backup),
        "weekly_automation_modified": False,
        "run_at_load": False,
    }, indent=2))

    return 0


def uninstall() -> int:
    if not PLIST_PATH.is_file():
        print(
            "No daily refresh plist found."
        )
        return 0

    if is_loaded():
        result = command(
            "launchctl",
            "bootout",
            DOMAIN,
            str(PLIST_PATH),
        )

        if result.returncode != 0:
            print(
                "ERROR: Could not unload service."
            )
            return 1

    PLIST_PATH.unlink()

    print(json.dumps({
        "status": "UNINSTALLED",
        "label": LABEL,
        "weekly_automation_modified": False,
        "logs_preserved": True,
        "audit_history_preserved": True,
    }, indent=2))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="INNEVA.E daily scheduler"
    )

    parser.add_argument(
        "action",
        choices=[
            "install",
            "update",
            "status",
            "uninstall",
        ],
    )

    args = parser.parse_args()

    if args.action == "install":
        return install()

    if args.action == "update":
        return update()

    if args.action == "uninstall":
        return uninstall()

    print(json.dumps(
        service_status(),
        indent=2,
    ))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
