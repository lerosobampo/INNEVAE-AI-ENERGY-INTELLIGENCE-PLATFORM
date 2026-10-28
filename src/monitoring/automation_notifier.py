
"""
INNEVA.E - AUTOMATION NOTIFIER
Module 15 - Checkpoint 15.9D

Features:
- Reads automation health
- Sends macOS notifications through INNEVAE Notifier.app
- Prevents repeated alerts for the same problem
- Clears alert state when automation recovers
- Supports dry-run and real notification modes

The production execution database is read-only.
"""

import argparse
import json
import subprocess
import sys

from pathlib import Path

from automation_health_monitor import (
    load_execution_history,
    evaluate_health,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

STATE_DIRECTORY = (
    PROJECT_ROOT / "data" / "monitoring"
)

STATE_FILE = (
    STATE_DIRECTORY / "notification_state.json"
)


# ==========================================
# MACOS APPLICATION
# ==========================================

def find_notifier_app():

    home = Path.home()

    candidates = [
        home / "Applications" / "INNEVAE Notifier.app",
        Path("/Applications/INNEVAE Notifier.app"),
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        "INNEVAE Notifier.app was not found. "
        "Check your Applications folder."
    )


def send_macos_notification(notification):
    """
    Write the notification message to a local file,
    then launch the verified AppleScript application.
    """

    app_path = (
        Path.home()
        / "Desktop"
        / "INNEVAE File Notifier.app"
    )

    if not app_path.is_dir():
        raise FileNotFoundError(
            f"Notification application not found: {app_path}"
        )

    message_file = (
        PROJECT_ROOT
        / "data"
        / "monitoring"
        / "notification_message.txt"
    )

    message_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    message_file.write_text(
        notification["message"],
        encoding="utf-8",
    )

    subprocess.run(
        [
            "/usr/bin/open",
            "-n",
            str(app_path),
        ],
        check=True,
        timeout=15,
    )


# ==========================================
# NOTIFICATION CONTENT
# ==========================================

def build_notification(health_result):

    status = health_result["health"]

    if status == "healthy":
        return None

    if status == "warning":
        title = "INNEVA.E - Automation Warning"

    elif status == "critical":
        title = "INNEVA.E - Critical Automation Alert"

    else:
        return None

    issues = health_result.get("issues", [])

    message = (
        " ".join(issues)
        if issues
        else health_result.get(
            "reason",
            "Automation requires attention.",
        )
    )

    return {
        "title": title,
        "message": message[:240],
        "status": status,
    }


# ==========================================
# DEDUPLICATION
# ==========================================

def build_alert_key(health_result):
    """
    Identify the underlying problem.

    Same status + same latest execution +
    same issue text => same alert.
    """

    return json.dumps(
        {
            "status": health_result["health"],
            "latest_execution_id": (
                health_result.get(
                    "latest_execution_id"
                )
            ),
            "issues": health_result.get(
                "issues", []
            ),
            "reason": health_result.get(
                "reason"
            ),
        },
        sort_keys=True,
    )


def load_notification_state():

    if not STATE_FILE.exists():
        return {}

    with STATE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_notification_state(state):

    STATE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = STATE_FILE.with_suffix(
        ".tmp"
    )

    temporary_file.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    temporary_file.replace(STATE_FILE)


# ==========================================
# NOTIFICATION CONTROLLER
# ==========================================

def process_health_result(
    health_result,
    notify=False,
):

    status = health_result["health"]

    if status == "healthy":

        if notify:
            save_notification_state({})

        return {
            "action": "no_alert",
            "health": status,
            "message": "Automation is healthy.",
        }

    notification = build_notification(
        health_result
    )

    if notification is None:
        return {
            "action": "no_alert",
            "health": status,
        }

    alert_key = build_alert_key(
        health_result
    )

    previous_state = load_notification_state()

    if (
        previous_state.get("last_alert_key")
        == alert_key
    ):
        return {
            "action": "duplicate_suppressed",
            "health": status,
            "notification": notification,
        }

    if not notify:
        return {
            "action": "dry_run",
            "health": status,
            "notification": notification,
        }

    send_macos_notification(notification)

    save_notification_state(
        {
            "last_alert_key": alert_key,
            "last_status": status,
            "last_execution_id": (
                health_result.get(
                    "latest_execution_id"
                )
            ),
        }
    )

    return {
        "action": "notification_submitted",
        "health": status,
        "notification": notification,
    }


# ==========================================
# MAIN
# ==========================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send macOS notifications.",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("INNEVA.E - AUTOMATION NOTIFIER")
    print("=" * 65)

    try:
        history = load_execution_history()

        health_result = evaluate_health(
            history
        )

        result = process_health_result(
            health_result,
            notify=args.notify,
        )

        print(
            json.dumps(result, indent=2)
        )

        if health_result["health"] == "healthy":
            return 0

        if health_result["health"] == "warning":
            return 1

        return 2

    except Exception as error:

        print(
            f"Notification error: {error}",
            file=sys.stderr,
        )

        return 3


if __name__ == "__main__":
    raise SystemExit(main())
