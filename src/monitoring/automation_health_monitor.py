
"""
INNEVA.E - AUTOMATION HEALTH MONITOR
Module 15 - Checkpoint 15.9A

Monitors:
1. Latest execution status
2. Latest successful report
3. Age of the latest successful report
4. Consecutive execution failures

Uses the existing SQLite execution history.

No Ollama calls are required.
No database records are modified.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# ==========================================
# CONFIGURATION
# ==========================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "innevae_platform.db"
)

AUTOMATION_NAME = "energy_intelligence_report"

# Weekly report schedule: Monday 09:00.
# Allow 8 days before declaring the latest
# successful report overdue.
MAX_REPORT_AGE_HOURS = 8 * 24

# Two consecutive failures trigger CRITICAL.
CRITICAL_FAILURE_THRESHOLD = 2


# ==========================================
# TIME UTILITIES
# ==========================================

def parse_timestamp(value):
    if not value:
        return None

    try:
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        return timestamp.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


# ==========================================
# DATABASE
# ==========================================

def load_execution_history():

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Automation database not found: {DATABASE_PATH}"
        )

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                execution_id,
                started_at_utc,
                finished_at_utc,
                status,
                report_path,
                error_message
            FROM automation_execution_log
            WHERE automation_name = ?
            ORDER BY execution_id DESC
            """,
            (AUTOMATION_NAME,),
        ).fetchall()

    return [dict(row) for row in rows]


# ==========================================
# HEALTH EVALUATION
# ==========================================

def evaluate_health(history, now=None):

    now = now or datetime.now(timezone.utc)

    if not history:
        return {
            "health": "critical",
            "reason": "No automation executions found.",
            "execution_count": 0,
        }

    latest_execution = history[0]

    latest_success = next(
        (
            record
            for record in history
            if record["status"] == "success"
            and record["report_path"]
            and str(record["report_path"]).startswith(
                str(PROJECT_ROOT / "reports")
            )
            and Path(record["report_path"]).is_file()
        ),
        None,
    )

    consecutive_failures = 0

    for record in history:
        if record["status"] == "failed":
            consecutive_failures += 1
        else:
            break

    latest_success_age_hours = None

    if latest_success:

        success_timestamp = parse_timestamp(
            latest_success["finished_at_utc"]
        )

        if success_timestamp:

            latest_success_age_hours = round(
                (
                    now - success_timestamp
                ).total_seconds() / 3600,
                2,
            )

    issues = []

    if consecutive_failures >= CRITICAL_FAILURE_THRESHOLD:
        issues.append(
            f"{consecutive_failures} consecutive failures."
        )

    if latest_success is None:
        issues.append(
            "No successful report with an existing "
            "production report file was found."
        )

    elif latest_success_age_hours is None:
        issues.append(
            "Latest successful report has an "
            "invalid completion timestamp."
        )

    elif latest_success_age_hours > MAX_REPORT_AGE_HOURS:
        issues.append(
            "Latest successful report is overdue."
        )

    if consecutive_failures >= CRITICAL_FAILURE_THRESHOLD:
        health = "critical"

    elif latest_success is None:
        health = "critical"

    elif (
        latest_success_age_hours is None
        or latest_success_age_hours > MAX_REPORT_AGE_HOURS
    ):
        health = "critical"

    elif latest_execution["status"] != "success":
        health = "warning"
        issues.append(
            "Latest execution did not succeed."
        )

    else:
        health = "healthy"

    return {
        "health": health,
        "checked_at_utc": now.isoformat(),
        "automation_name": AUTOMATION_NAME,
        "execution_count": len(history),
        "latest_execution_id": latest_execution[
            "execution_id"
        ],
        "latest_execution_status": latest_execution[
            "status"
        ],
        "latest_execution_error": latest_execution[
            "error_message"
        ],
        "latest_success_id": (
            latest_success["execution_id"]
            if latest_success
            else None
        ),
        "latest_success_report": (
            latest_success["report_path"]
            if latest_success
            else None
        ),
        "latest_success_age_hours": (
            latest_success_age_hours
        ),
        "consecutive_failures": consecutive_failures,
        "issues": issues,
        "report_age_threshold_hours": MAX_REPORT_AGE_HOURS,
        "note": (
            "This monitors automation execution history, "
            "not the freshness of the underlying energy data. "
            "Historical test executions may remain in the log."
        ),
    }


# ==========================================
# MAIN
# ==========================================

def main():

    print("=" * 65)
    print("INNEVA.E - AUTOMATION HEALTH MONITOR")
    print("=" * 65)

    try:
        history = load_execution_history()
        result = evaluate_health(history)

    except (OSError, sqlite3.Error) as error:
        result = {
            "health": "critical",
            "reason": str(error),
        }

    print(json.dumps(result, indent=2))

    if result["health"] == "healthy":
        return 0

    if result["health"] == "warning":
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
