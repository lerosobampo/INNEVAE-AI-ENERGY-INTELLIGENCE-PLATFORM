
"""INNEVA.E — Checkpoint 20.5C.2: Data Refresh Monitoring.

Read-only Streamlit page for daily refresh operations.

Uses the existing refresh_monitor.py engine.
Does not modify datasets, SQLite databases, or launchd jobs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[3]
AUTOMATION_DIR = ROOT / "src" / "automation"

if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from refresh_monitor import (
    load_daily_history,
    load_refresh_audit,
    monitor,
)


st.set_page_config(
    page_title="INNEVA.E | Data Refresh Monitoring",
    page_icon="🔄",
    layout="wide",
)


def format_timestamp(value):
    if not value:
        return "Not available"

    try:
        parsed = pd.to_datetime(
            value,
            utc=True,
        )

        return parsed.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

    except (ValueError, TypeError):
        return str(value)


def show_health(status):
    if status == "HEALTHY":
        st.success(
            "Operational health: HEALTHY"
        )

    elif status == "WARNING":
        st.warning(
            "Operational health: WARNING"
        )

    elif status == "CRITICAL":
        st.error(
            "Operational health: CRITICAL"
        )

    else:
        st.info(
            f"Operational health: {status}"
        )


def show_schedule(schedule):
    st.subheader("Daily Scheduler")

    status = schedule.get(
        "status",
        "UNKNOWN",
    )

    if status == "VERIFIED":
        st.success(
            "Scheduled execution verified."
        )

    elif status == "NOT_DUE":
        st.info(
            "The next scheduled execution "
            "is not due yet."
        )

    elif status == "UNVERIFIED":
        st.warning(
            "Scheduled execution is unverified."
        )

    else:
        st.warning(
            f"Scheduler status: {status}"
        )

    st.write(
        "**Schedule:** 07:00 Europe/Amsterdam"
    )

    st.write(
        "**Latest due date:**",
        schedule.get("latest_due_date")
        or "Not yet due",
    )

    st.caption(
        schedule.get(
            "reason",
            "No scheduler details available.",
        )
    )

    st.caption(
        "The existing runner does not yet record "
        "whether an execution was triggered by "
        "launchd or manually. An unverified run "
        "is not proof of scheduler failure."
    )


def show_alerts(alerts):
    st.subheader("Operational Alerts")

    if not alerts:
        st.success(
            "No active operational alerts."
        )
        return

    for alert in alerts:
        severity = alert.get(
            "severity",
            "WARNING",
        )

        code = alert.get(
            "code",
            "UNKNOWN",
        )

        message = alert.get(
            "message",
            "No details available.",
        )

        text = f"{code}: {message}"

        if severity == "CRITICAL":
            st.error(text)

        elif severity == "WARNING":
            st.warning(text)

        else:
            st.info(text)


def show_execution_history():
    st.subheader("Daily Execution History")

    records, errors = load_daily_history()

    if errors:
        for error in errors:
            st.warning(error)

    if not records:
        st.info(
            "No daily refresh executions "
            "have been recorded."
        )
        return

    rows = []

    for record in records:
        rows.append({
            "Started (UTC)": format_timestamp(
                record.get("started_at_utc")
            ),
            "Finished (UTC)": format_timestamp(
                record.get("finished_at_utc")
            ),
            "Status": record.get(
                "status",
                "UNKNOWN",
            ),
            "Source": record.get(
                "execution_source",
                "UNKNOWN",
            ),
            "Incoming before": len(
                record.get(
                    "incoming_files_before"
                ) or []
            ),
            "Incoming after": len(
                record.get(
                    "incoming_files_after"
                ) or []
            ),
        })

    history = pd.DataFrame(rows)

    st.dataframe(
        history,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Export execution history (CSV)",
        data=history.to_csv(
            index=False
        ).encode("utf-8"),
        file_name=(
            "innevae_daily_refresh_history.csv"
        ),
        mime="text/csv",
    )

    with st.expander(
        "Latest execution — full record"
    ):
        st.json(records[0])


def show_ingestion_audit():
    st.subheader("Ingestion Audit History")

    audit = load_refresh_audit(limit=100)

    if audit.get("error"):
        st.error(
            "Unable to read refresh audit: "
            f"{audit['error']}"
        )
        return

    if not audit.get("database_exists"):
        st.info(
            "Refresh audit database "
            "has not been created."
        )
        return

    counts = audit.get(
        "status_counts",
        {},
    )

    a, b, c = st.columns(3)

    a.metric(
        "Applied",
        counts.get("APPLIED", 0),
    )

    b.metric(
        "Rejected",
        counts.get("REJECTED", 0),
    )

    c.metric(
        "Errors",
        counts.get("ERROR", 0),
    )

    attempts = audit.get(
        "recent_attempts",
        [],
    )

    if not attempts:
        st.info(
            "No ingestion attempts recorded."
        )
        return

    rows = []

    for attempt in attempts:
        rows.append({
            "Attempted (UTC)": format_timestamp(
                attempt.get("attempted_at_utc")
            ),
            "Candidate": attempt.get(
                "candidate_name"
            ),
            "Status": attempt.get(
                "status"
            ),
            "Attempt ID": attempt.get(
                "attempt_id"
            ),
            "Ingestion run": attempt.get(
                "ingestion_run_id"
            ),
        })

    frame = pd.DataFrame(rows)

    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Export ingestion audit (CSV)",
        data=frame.to_csv(
            index=False
        ).encode("utf-8"),
        file_name=(
            "innevae_refresh_audit.csv"
        ),
        mime="text/csv",
    )

    attempt_ids = [
        item["attempt_id"]
        for item in attempts
    ]

    selected_id = st.selectbox(
        "Inspect an ingestion attempt",
        attempt_ids,
        format_func=lambda attempt_id: next(
            (
                f"{item['status']} — "
                f"{item['candidate_name']} — "
                f"{attempt_id[:8]}"
            )
            for item in attempts
            if item["attempt_id"] == attempt_id
        ),
    )

    selected = next(
        item
        for item in attempts
        if item["attempt_id"] == selected_id
    )

    st.json(selected)

    st.caption(
        "Historical rejected attempts remain "
        "visible even after a successful retry. "
        "They are not necessarily active failures."
    )


def render():
    st.title("Data Refresh Monitoring")

    st.caption(
        "INNEVA.E | Local operational monitoring | "
        "Read-only dashboard"
    )

    if st.button(
        "Refresh monitoring",
        type="primary",
    ):
        st.rerun()

    try:
        result = monitor()

    except Exception as error:
        st.error(
            "Unable to evaluate refresh monitoring: "
            f"{type(error).__name__}: {error}"
        )
        return

    show_health(
        result.get("health", "UNKNOWN")
    )

    st.caption(
        "Last checked: "
        + format_timestamp(
            result.get("checked_at_utc")
        )
    )

    st.divider()

    latest = result.get("latest_run") or {}

    integrity = result.get(
        "production_integrity",
        {},
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Operational health",
        result.get("health", "UNKNOWN"),
    )

    m2.metric(
        "Daily executions",
        result.get(
            "total_recorded_runs",
            0,
        ),
    )

    m3.metric(
        "Production integrity",
        integrity.get(
            "status",
            "UNKNOWN",
        ),
    )

    m4.metric(
        "Active alerts",
        result.get(
            "alert_count",
            0,
        ),
    )

    st.divider()

    show_schedule(
        result.get("schedule", {})
    )

    st.divider()

    show_alerts(
        result.get("alerts", [])
    )

    st.divider()

    st.subheader("Latest Refresh Execution")

    if latest:
        st.write(
            "**Status:**",
            latest.get(
                "status",
                "UNKNOWN",
            ),
        )

        st.write(
            "**Started:**",
            format_timestamp(
                latest.get("started_at_utc")
            ),
        )

        st.write(
            "**Execution source:**",
            latest.get(
                "execution_source",
                "UNKNOWN",
            ),
        )

    else:
        st.info(
            "No execution history available."
        )

    st.divider()

    st.subheader("Dataset Protection")

    if integrity.get("status") == "PASS":
        st.success(
            "Production dataset SHA-256 "
            "matches the protected baseline."
        )
    else:
        st.error(
            integrity.get(
                "reason",
                "Production integrity could "
                "not be verified.",
            )
        )

    st.write(
        "**Development dataset exists:**",
        result.get(
            "development_exists",
            False,
        ),
    )

    pending = result.get(
        "pending_csv_files",
        [],
    )

    st.write(
        "**Pending incoming CSV files:**",
        len(pending),
    )

    if pending:
        st.dataframe(
            pd.DataFrame({
                "Pending CSV": pending
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    show_execution_history()

    st.divider()

    show_ingestion_audit()

    st.divider()

    st.caption(
        "This dashboard does not execute refreshes, "
        "modify data, change launchd schedules, "
        "or send automatic notifications."
    )


render()
