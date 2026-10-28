
"""INNEVA.E — Checkpoint 20.5C.3C: local refresh alerts.

Read-only monitoring with macOS notifications.

Features:
- Uses the existing refresh monitoring engine.
- Sends notifications for CRITICAL alerts.
- Deduplicates incidents using a stable fingerprint.
- Preserves a JSONL notification audit.
- Uses a file lock to prevent concurrent checks.
- Supports dry-run testing without notifications.
- Does not modify datasets or launchd services.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from refresh_monitor import monitor


ROOT = Path(__file__).resolve().parents[2]

ALERT_DIR = (
    ROOT / "reports" / "data_quality"
    / "refresh_alerts"
)

HISTORY_FILE = ALERT_DIR / "notification_history.jsonl"
LOCK_FILE = ALERT_DIR / "refresh_alerts.lock"

SUCCESSFUL_DELIVERY = "SENT"
DEDUPLICATED = "SUPPRESSED_DUPLICATE"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_history(record: dict) -> None:
    ALERT_DIR.mkdir(parents=True, exist_ok=True)

    with HISTORY_FILE.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                record,
                ensure_ascii=False,
            ) + "\n"
        )


def read_history() -> list[dict]:
    if not HISTORY_FILE.is_file():
        return []

    records = []

    with HISTORY_FILE.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    records.append(record)
            except json.JSONDecodeError:
                continue

    return records


def incident_fingerprint(alert: dict, report: dict) -> str:
    """Identify an incident independently of check time."""

    code = str(alert.get("code", "UNKNOWN"))

    if code.startswith("SCHEDULED_EXECUTION_"):
        subject = (
            report.get("schedule", {}).get(
                "latest_due_date"
            )
            or "UNKNOWN_DATE"
        )

    elif code == "PRODUCTION_INTEGRITY_FAILED":
        subject = (
            report.get("production_integrity", {}).get(
                "sha256"
            )
            or "MISSING"
        )

    elif code == "LATEST_REFRESH_FAILED":
        subject = (
            report.get("latest_run", {}).get(
                "started_at_utc"
            )
            or "UNKNOWN_RUN"
        )

    else:
        subject = str(
            alert.get("message", "")
        )

    payload = f"{code}|{subject}"

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def already_notified(
    fingerprint: str,
    history: list[dict],
) -> bool:
    return any(
        record.get("fingerprint") == fingerprint
        and record.get("status") == SUCCESSFUL_DELIVERY
        for record in history
    )


def notify_macos(
    title: str,
    message: str,
) -> tuple[bool, str]:
    """Request a local notification using osascript.

    A zero exit code means macOS accepted the
    AppleScript command; it does not guarantee
    the banner was displayed to the user.
    """
    script = (
        "on run argv\n"
        "set notificationTitle to item 1 of argv\n"
        "set notificationBody to item 2 of argv\n"
        "display notification notificationBody "
        "with title notificationTitle\n"
        "end run"
    )

    try:
        result = subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                script,
                title,
                message,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

        return (
            result.returncode == 0,
            (
                result.stderr.strip()
                if result.returncode != 0
                else ""
            ),
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        return False, str(error)


def run_check(
    dry_run: bool = False,
) -> dict:
    """Evaluate alerts under an exclusive process lock."""

    ALERT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOCK_FILE.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        try:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

        except BlockingIOError:
            return {
                "status": "ALREADY_RUNNING",
                "checked_at_utc": now_utc(),
            }

        try:
            report = monitor()
            history = read_history()

            critical_alerts = [
                alert
                for alert in report.get("alerts", [])
                if alert.get("severity") == "CRITICAL"
            ]

            results = []

            for alert in critical_alerts:
                fingerprint = incident_fingerprint(
                    alert,
                    report,
                )

                if already_notified(
                    fingerprint,
                    history,
                ):
                    status = DEDUPLICATED
                    error = None

                elif dry_run:
                    status = "DRY_RUN"
                    error = None

                else:
                    title = "INNEVA.E — Critical Alert"
                    message = (
                        f"{alert.get('code', 'UNKNOWN')}: "
                        f"{alert.get('message', '')}"
                    )

                    success, error = notify_macos(
                        title,
                        message[:240],
                    )

                    status = (
                        SUCCESSFUL_DELIVERY
                        if success
                        else "NOTIFICATION_FAILED"
                    )

                record = {
                    "checked_at_utc": now_utc(),
                    "fingerprint": fingerprint,
                    "severity": "CRITICAL",
                    "code": alert.get("code"),
                    "message": alert.get("message"),
                    "status": status,
                    "error": error,
                }

                results.append(record)

                if not dry_run:
                    append_history(record)
                    history.append(record)

            return {
                "status": (
                    "CRITICAL_ALERTS"
                    if critical_alerts
                    else "NO_CRITICAL_ALERTS"
                ),
                "checked_at_utc": now_utc(),
                "health": report["health"],
                "dry_run": dry_run,
                "critical_alert_count": len(
                    critical_alerts
                ),
                "notifications": results,
            }

        finally:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="INNEVA.E local refresh alerts"
    )

    parser.add_argument(
        "action",
        choices=[
            "check",
            "history",
            "status",
            "test-notification",
        ],
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    if args.action == "history":
        records = read_history()

        print(json.dumps({
            "notifications": records[
                -args.limit:
            ][::-1],
        }, indent=2))

        return 0

    if args.action == "status":
        records = read_history()

        print(json.dumps({
            "history_path": str(HISTORY_FILE),
            "total_history_records": len(records),
            "successful_notifications": sum(
                record.get("status") == "SENT"
                for record in records
            ),
        }, indent=2))

        return 0

    if args.action == "test-notification":
        if args.dry_run:
            print(json.dumps({
                "status": "DRY_RUN",
                "message": (
                    "Test notification was not sent"
                ),
            }, indent=2))
            return 0

        success, error = notify_macos(
            "INNEVA.E — Notification Test",
            "Local operational notifications are working.",
        )

        print(json.dumps({
            "status": (
                "SENT" if success
                else "NOTIFICATION_FAILED"
            ),
            "error": error,
        }, indent=2))

        return 0 if success else 1

    result = run_check(
        dry_run=args.dry_run
    )

    print(json.dumps(
        result,
        indent=2,
    ))

    if result["status"] == "ALREADY_RUNNING":
        return 1

    if any(
        record["status"] == "NOTIFICATION_FAILED"
        for record in result.get("notifications", [])
    ):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
