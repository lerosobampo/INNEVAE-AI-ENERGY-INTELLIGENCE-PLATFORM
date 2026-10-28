
"""INNEVA.E — Checkpoint 20.5C.3B: refresh monitoring.

Read-only operational monitoring for:
- Daily refresh execution history
- Scheduled execution timing and outcomes
- Production dataset integrity
- SQLite ingestion audit history
- Pending CSV backlog
- Operational alerts

Schedule: 07:00 Europe/Amsterdam.
Allowed start window: 07:00–08:00 local time.

This monitor does not modify datasets, databases,
launchd jobs, or execution history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import (
    date,
    datetime,
    time,
    timedelta,
    timezone,
)
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]

LOCAL_TIMEZONE = ZoneInfo("Europe/Amsterdam")

DAILY_LOG = (
    ROOT / "reports" / "data_quality"
    / "daily_refresh" / "daily_refresh_runs.jsonl"
)

REFRESH_DB = (
    ROOT / "reports" / "data_quality"
    / "refresh_history.sqlite3"
)

PRODUCTION = (
    ROOT / "data" / "forecasting"
    / "energy_intelligence_hourly.csv"
)

DEVELOPMENT = (
    ROOT / "data" / "staging"
    / "energy_intelligence_hourly_development.csv"
)

INCOMING = ROOT / "data" / "refresh" / "incoming"

EXPECTED_PRODUCTION_SHA256 = (
    "5b1c051071a497493a37121420c7ee5944814362464c"
    "394bc4082f306653684e"
)

FIRST_SCHEDULED_DATE = date(2026, 10, 27)

SCHEDULE_HOUR = 7
SCHEDULE_MINUTE = 0

GRACE_PERIOD_MINUTES = 60

SUCCESS_STATUSES = {
    "COMPLETE",
    "NO_NEW_DATA",
}

FAILURE_STATUSES = {
    "ERROR",
    "REFRESH_ERROR",
    "REFRESH_NOT_COMPLETE",
    "UNEXPECTED_REFRESH_OUTPUT",
    "CRITICAL_PRODUCTION_HASH_CHANGED",
}

AUDIT_FAILURE_STATUSES = {
    "ERROR",
    "REJECTED",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value)
        )

        if parsed.tzinfo is None:
            return None

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_daily_history():
    if not DAILY_LOG.is_file():
        return [], []

    records = []
    errors = []

    with DAILY_LOG.open(
        "r",
        encoding="utf-8",
    ) as handle:

        for line_number, line in enumerate(
            handle,
            1,
        ):
            if not line.strip():
                continue

            try:
                record = json.loads(line)

                if not isinstance(record, dict):
                    raise ValueError(
                        "Expected JSON object"
                    )

                record = dict(record)

                record.setdefault(
                    "execution_source",
                    "UNKNOWN",
                )

                records.append(record)

            except (
                json.JSONDecodeError,
                ValueError,
            ) as error:
                errors.append(
                    f"Line {line_number}: {error}"
                )

    minimum = datetime.min.replace(
        tzinfo=timezone.utc
    )

    records.sort(
        key=lambda record: (
            parse_timestamp(
                record.get("started_at_utc")
            ) or minimum
        ),
        reverse=True,
    )

    return records, errors


def load_refresh_audit(limit=20):
    if not REFRESH_DB.is_file():
        return {
            "database_exists": False,
            "recent_attempts": [],
            "status_counts": {},
            "error": None,
        }

    connection = None

    try:
        connection = sqlite3.connect(
            f"file:{REFRESH_DB.resolve()}?mode=ro",
            uri=True,
        )

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                attempt_id,
                attempted_at_utc,
                candidate_name,
                candidate_sha256,
                status,
                destination,
                ingestion_run_id,
                details_json
            FROM refresh_attempts
            ORDER BY attempted_at_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        counts = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM refresh_attempts
            GROUP BY status
            """
        ).fetchall()

        attempts = []

        for row in rows:
            item = dict(row)

            raw_details = item.pop(
                "details_json",
                None,
            )

            if raw_details:
                try:
                    item["details"] = json.loads(
                        raw_details
                    )

                except json.JSONDecodeError:
                    item["details"] = {
                        "unreadable_json": True
                    }

            else:
                item["details"] = None

            attempts.append(item)

        return {
            "database_exists": True,
            "recent_attempts": attempts,
            "status_counts": {
                row["status"]: row["count"]
                for row in counts
            },
            "error": None,
        }

    except sqlite3.Error as error:
        return {
            "database_exists": True,
            "recent_attempts": [],
            "status_counts": {},
            "error": str(error),
        }

    finally:
        if connection is not None:
            connection.close()


def production_integrity():
    if not PRODUCTION.is_file():
        return {
            "status": "FAIL",
            "reason": "Production dataset missing",
            "sha256": None,
        }

    try:
        actual_hash = sha256(PRODUCTION)

    except OSError as error:
        return {
            "status": "FAIL",
            "reason": str(error),
            "sha256": None,
        }

    matches = (
        actual_hash
        == EXPECTED_PRODUCTION_SHA256
    )

    return {
        "status": (
            "PASS" if matches else "FAIL"
        ),
        "reason": (
            "Production baseline verified"
            if matches
            else "Production SHA-256 mismatch"
        ),
        "sha256": actual_hash,
    }


def schedule_window(day: date):
    """Return the local scheduled time and deadline.

    Compare UTC instants to handle timezone offsets
    and daylight-saving transitions correctly.
    """
    start_local = datetime.combine(
        day,
        time(
            SCHEDULE_HOUR,
            SCHEDULE_MINUTE,
        ),
        tzinfo=LOCAL_TIMEZONE,
    )

    start_utc = start_local.astimezone(
        timezone.utc
    )

    deadline_utc = (
        start_utc
        + timedelta(
            minutes=GRACE_PERIOD_MINUTES
        )
    )

    return start_utc, deadline_utc


def scheduled_execution_state(
    current,
    records,
):
    """Evaluate the most recent due scheduled date.

    A successful run is VERIFIED only when:
    - execution_source is LAUNCHD;
    - start time is inside the scheduled window;
    - completion time is valid;
    - final status is successful.

    Manual and legacy UNKNOWN runs never verify
    the scheduled execution.
    """
    current = current.astimezone(timezone.utc)

    local_now = current.astimezone(
        LOCAL_TIMEZONE
    )

    today = local_now.date()

    if today < FIRST_SCHEDULED_DATE:
        return {
            "status": "NOT_DUE",
            "reason": (
                "First scheduled execution is "
                f"{FIRST_SCHEDULED_DATE}"
            ),
            "latest_due_date": None,
            "execution_count": 0,
        }

    _, today_deadline = schedule_window(
        today
    )

    if current < today_deadline:
        due_date = today - timedelta(days=1)
    else:
        due_date = today

    if due_date < FIRST_SCHEDULED_DATE:
        return {
            "status": "NOT_DUE",
            "reason": (
                "First scheduled execution "
                "has not reached its deadline"
            ),
            "latest_due_date": None,
            "execution_count": 0,
        }

    scheduled_start, deadline = (
        schedule_window(due_date)
    )

    # Collect all launchd-labeled records that
    # started on the due local calendar date.
    matching = []

    for record in records:
        if record.get(
            "execution_source"
        ) != "LAUNCHD":
            continue

        started = parse_timestamp(
            record.get("started_at_utc")
        )

        if started is None:
            continue

        local_started = started.astimezone(
            LOCAL_TIMEZONE
        )

        if local_started.date() == due_date:
            matching.append(record)

    matching.sort(
        key=lambda record: (
            parse_timestamp(
                record.get("started_at_utc")
            )
        ),
        reverse=True,
    )

    base = {
        "latest_due_date": due_date.isoformat(),
        "scheduled_start_utc": (
            scheduled_start.isoformat()
        ),
        "deadline_utc": deadline.isoformat(),
        "execution_count": len(matching),
    }

    if not matching:
        return {
            **base,
            "status": "MISSED",
            "reason": (
                "No LAUNCHD-labeled execution "
                "was recorded for the latest "
                "due scheduled date"
            ),
        }

    on_time_successes = []
    on_time_failures = []
    late_successes = []
    late_failures = []
    incomplete = []

    for record in matching:
        started = parse_timestamp(
            record.get("started_at_utc")
        )

        finished = parse_timestamp(
            record.get("finished_at_utc")
        )

        status = record.get(
            "status",
            "UNKNOWN",
        )

        valid_completion = (
            finished is not None
            and finished >= started
            and finished <= current
        )

        on_time = (
            scheduled_start
            <= started
            <= deadline
        )

        successful = (
            status in SUCCESS_STATUSES
            and valid_completion
        )

        failed = (
            status in FAILURE_STATUSES
        )

        if successful and on_time:
            on_time_successes.append(record)

        elif failed and on_time:
            on_time_failures.append(record)

        elif successful:
            late_successes.append(record)

        elif failed:
            late_failures.append(record)

        else:
            incomplete.append(record)

    # A successful on-time execution satisfies
    # the scheduled requirement even if another
    # attempt on that date failed.
    if on_time_successes:
        selected = on_time_successes[0]

        return {
            **base,
            "status": "VERIFIED",
            "reason": (
                "A successful LAUNCHD execution "
                "started inside the permitted "
                "07:00–08:00 local window"
            ),
            "matched_execution": selected,
        }

    if on_time_failures:
        selected = on_time_failures[0]

        return {
            **base,
            "status": "FAILED",
            "reason": (
                "A scheduled execution started "
                "on time but failed: "
                f"{selected.get('status')}"
            ),
            "matched_execution": selected,
        }

    if late_successes:
        selected = late_successes[0]

        return {
            **base,
            "status": "LATE",
            "reason": (
                "A successful LAUNCHD-labeled "
                "execution occurred outside "
                "the permitted start window"
            ),
            "matched_execution": selected,
        }

    if late_failures:
        selected = late_failures[0]

        return {
            **base,
            "status": "FAILED",
            "reason": (
                "A LAUNCHD-labeled execution "
                "occurred outside the scheduled "
                "window and failed"
            ),
            "matched_execution": selected,
        }

    return {
        **base,
        "status": "UNVERIFIED",
        "reason": (
            "LAUNCHD-labeled execution records "
            "exist, but none has a recognized "
            "successful or failed final outcome"
        ),
        "incomplete_execution_count": len(
            incomplete
        ),
    }


def monitor():
    current = utc_now()

    records, log_errors = (
        load_daily_history()
    )

    audit = load_refresh_audit()

    alerts = []

    for error in log_errors:
        alerts.append({
            "severity": "WARNING",
            "code": "INVALID_DAILY_LOG",
            "message": error,
        })

    latest = (
        records[0] if records else None
    )

    if latest:
        latest_status = latest.get(
            "status",
            "UNKNOWN",
        )

        if latest_status in FAILURE_STATUSES:
            alerts.append({
                "severity": "CRITICAL",
                "code": "LATEST_REFRESH_FAILED",
                "message": (
                    "Latest daily refresh: "
                    f"{latest_status}"
                ),
            })

        elif latest_status not in SUCCESS_STATUSES:
            alerts.append({
                "severity": "WARNING",
                "code": "UNKNOWN_REFRESH_STATUS",
                "message": latest_status,
            })

    schedule = scheduled_execution_state(
        current,
        records,
    )

    schedule_status = schedule["status"]

    if schedule_status in {
        "MISSED",
        "FAILED",
    }:
        alerts.append({
            "severity": "CRITICAL",
            "code": (
                "SCHEDULED_EXECUTION_"
                + schedule_status
            ),
            "message": schedule["reason"],
        })

    elif schedule_status in {
        "LATE",
        "UNVERIFIED",
    }:
        alerts.append({
            "severity": "WARNING",
            "code": (
                "SCHEDULED_EXECUTION_"
                + schedule_status
            ),
            "message": schedule["reason"],
        })

    integrity = production_integrity()

    if integrity["status"] != "PASS":
        alerts.append({
            "severity": "CRITICAL",
            "code": "PRODUCTION_INTEGRITY_FAILED",
            "message": integrity["reason"],
        })

    if not DEVELOPMENT.is_file():
        alerts.append({
            "severity": "CRITICAL",
            "code": "DEVELOPMENT_DATASET_MISSING",
            "message": (
                "Development dataset missing"
            ),
        })

    if audit["error"]:
        alerts.append({
            "severity": "WARNING",
            "code": "REFRESH_AUDIT_UNREADABLE",
            "message": audit["error"],
        })

    recent_failures = [
        attempt
        for attempt in audit["recent_attempts"]
        if attempt.get("status")
        in AUDIT_FAILURE_STATUSES
    ]

    latest_attempt = (
        audit["recent_attempts"][0]
        if audit["recent_attempts"]
        else None
    )

    if (
        latest_attempt
        and latest_attempt.get("status")
        in AUDIT_FAILURE_STATUSES
    ):
        alerts.append({
            "severity": "WARNING",
            "code": "LATEST_INGESTION_ATTEMPT_FAILED",
            "message": (
                "Latest ingestion attempt: "
                f"{latest_attempt['status']}"
            ),
        })

    pending_files = (
        sorted(
            path.name
            for path in INCOMING.glob("*.csv")
            if path.is_file()
        )
        if INCOMING.is_dir()
        else []
    )

    if len(pending_files) >= 5:
        alerts.append({
            "severity": "WARNING",
            "code": "REFRESH_BACKLOG",
            "message": (
                f"{len(pending_files)} CSV files "
                "awaiting processing"
            ),
        })

    if any(
        alert["severity"] == "CRITICAL"
        for alert in alerts
    ):
        health = "CRITICAL"

    elif alerts:
        health = "WARNING"

    else:
        health = "HEALTHY"

    return {
        "checked_at_utc": current.isoformat(),
        "health": health,
        "timezone": str(LOCAL_TIMEZONE),
        "daily_schedule": (
            "07:00 Europe/Amsterdam"
        ),
        "schedule": schedule,
        "latest_run": latest,
        "total_recorded_runs": len(records),
        "production_integrity": integrity,
        "development_exists": (
            DEVELOPMENT.is_file()
        ),
        "pending_csv_files": pending_files,
        "refresh_audit": {
            "database_exists": audit[
                "database_exists"
            ],
            "status_counts": audit[
                "status_counts"
            ],
            "latest_attempt": latest_attempt,
            "recent_failure_count": len(
                recent_failures
            ),
            "error": audit["error"],
        },
        "alerts": alerts,
        "alert_count": len(alerts),
    }


def main():
    parser = argparse.ArgumentParser(
        description="INNEVA.E refresh monitoring"
    )

    parser.add_argument(
        "action",
        choices=[
            "check",
            "history",
            "audit",
        ],
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    if args.action == "history":
        records, errors = (
            load_daily_history()
        )

        print(json.dumps({
            "runs": records[:args.limit],
            "errors": errors,
        }, indent=2))

        return 0

    if args.action == "audit":
        print(json.dumps(
            load_refresh_audit(args.limit),
            indent=2,
        ))

        return 0

    result = monitor()

    print(json.dumps(
        result,
        indent=2,
    ))

    return (
        1
        if result["health"] == "CRITICAL"
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
