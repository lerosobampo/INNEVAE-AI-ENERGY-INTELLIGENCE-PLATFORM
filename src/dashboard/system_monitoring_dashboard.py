
"""
INNEVA.E - SYSTEM MONITORING DASHBOARD
Module 16 - Checkpoint 16.5A

Displays:
- Automation execution statistics
- Recent execution history
- Execution details
- Validation and error information

Read-only monitoring.
"""

import json

import pandas as pd
import streamlit as st

from monitoring_analytics import render_monitoring_analytics

from monitoring_data import (
    load_execution_history,
    calculate_execution_metrics,
)

from health_monitoring_dashboard import (
    render_health_monitoring_dashboard,
)


def parse_json_field(value):
    """
    Decode JSON stored in SQLite.
    """

    if value is None or pd.isna(value):
        return None

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def render_system_monitoring_dashboard():

    st.header("System Monitoring")

    # ======================================
    # AUTOMATION HEALTH
    # ======================================

    render_health_monitoring_dashboard()

    st.divider()

    # ======================================
    # EXECUTION HISTORY
    # ======================================

    st.info(
        "Inspect historical automation executions "
        "recorded in the local SQLite database."
    )

    if st.button(
        "Refresh Execution History",
        key="refresh_execution_history",
    ):
        st.rerun()

    try:
        history = load_execution_history()

    except Exception as error:
        st.error(
            f"Unable to load execution history: {error}"
        )
        return

    metrics = calculate_execution_metrics(
        history
    )

        # ======================================
    # MONITORING ANALYTICS
    # ======================================

    render_monitoring_analytics(history)

    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Executions",
        metrics["total_executions"],
    )

    col2.metric(
        "Successful",
        metrics["successful_executions"],
    )

    col3.metric(
        "Failed",
        metrics["failed_executions"],
    )

    col4.metric(
        "Success Rate",
        f"{metrics['success_rate_pct']:.1f}%",
    )

    st.divider()

    st.subheader("Execution History")

    if history.empty:
        st.warning(
            "No automation executions were found."
        )
        return

    status_filter = st.selectbox(
        "Filter by status",
        options=[
            "All",
            "success",
            "failed",
        ],
        key="execution_status_filter",
    )

    filtered = history.copy()

    if status_filter != "All":
        filtered = filtered[
            filtered["status"] == status_filter
        ]

    display_columns = [
        "execution_id",
        "started_at_utc",
        "finished_at_utc",
        "status",
        "error_message",
    ]

    st.dataframe(
        filtered[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Execution Details")

    execution_ids = (
        history["execution_id"]
        .astype(int)
        .tolist()
    )

    selected_execution = st.selectbox(
        "Select execution ID",
        options=execution_ids,
        format_func=lambda value: f"Execution #{value}",
        key="selected_monitoring_execution",
    )

    selected = history.loc[
        history["execution_id"] == selected_execution
    ].iloc[0]

    st.write(
        "**Status:**",
        selected["status"],
    )

    st.write(
        "**Started (UTC):**",
        selected["started_at_utc"],
    )

    st.write(
        "**Finished (UTC):**",
        selected["finished_at_utc"],
    )

    if selected["error_message"]:
        st.error(
            selected["error_message"]
        )

    tools = parse_json_field(
        selected["executed_tools_json"]
    )

    validation = parse_json_field(
        selected["validation_json"]
    )

    with st.expander("Executed Tools"):
        st.json(
            tools if tools is not None else []
        )

    with st.expander("Validation Results"):
        st.json(
            validation if validation is not None else {}
        )

    with st.expander("Published Files"):

        st.write(
            "**Markdown:**",
            selected["report_path"],
        )

        st.write(
            "**JSON:**",
            selected["metadata_path"],
        )

    st.caption(
        "This page displays historical execution records. "
        "It does not currently evaluate scheduler health."
    )
