
"""
INNEVA.E - HEALTH MONITORING DASHBOARD
Module 16 - Checkpoint 16.5B

Integrates the existing automation health monitor
into Streamlit without duplicating health rules.

This module:
- Reads automation execution history
- Evaluates automation health
- Displays operational health indicators
- Does not modify the database
- Does not execute scheduled automations
"""

import sys
from pathlib import Path

import streamlit as st


# ==========================================
# PROJECT IMPORT CONFIGURATION
# ==========================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MONITORING_DIRECTORY = (
    PROJECT_ROOT / "src" / "monitoring"
)

if str(MONITORING_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(MONITORING_DIRECTORY),
    )

from automation_health_monitor import (
    load_execution_history,
    evaluate_health,
)


# ==========================================
# HEALTH DATA
# ==========================================

def get_automation_health():
    """
    Execute the existing health evaluation.

    Returns the original health-monitor
    result without changing its rules.
    """

    history = load_execution_history()

    return evaluate_health(history)


# ==========================================
# DISPLAY UTILITIES
# ==========================================

def format_report_age(value):

    if value is None:
        return "Unavailable"

    return f"{value:.2f} hours"


def format_execution_id(value):

    if value is None:
        return "Unavailable"

    return f"#{value}"


# ==========================================
# STREAMLIT DASHBOARD
# ==========================================

def render_health_monitoring_dashboard():

    st.subheader("Automation Health")

    st.caption(
        "Operational health calculated using the "
        "existing INNEVA.E automation health monitor."
    )

    try:
        health_data = get_automation_health()

    except Exception as error:

        st.error(
            "Unable to evaluate automation health: "
            f"{error}"
        )

        return

    health_status = health_data.get(
        "health",
        "unknown",
    )

    # --------------------------------------
    # 1. Overall health classification
    # --------------------------------------

    if health_status == "healthy":

        st.success(
            "HEALTHY — The latest execution succeeded "
            "and a sufficiently recent report exists."
        )

    elif health_status == "warning":

        st.warning(
            "WARNING — The automation requires attention."
        )

    elif health_status == "critical":

        st.error(
            "CRITICAL — The automation requires investigation."
        )

    else:

        st.error(
            f"Unknown health classification: {health_status}"
        )

    # --------------------------------------
    # 2. Operational indicators
    # --------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Latest Execution",
        format_execution_id(
            health_data.get("latest_execution_id")
        ),
    )

    col2.metric(
        "Latest Successful Report",
        format_execution_id(
            health_data.get("latest_success_id")
        ),
    )

    col3.metric(
        "Report Age",
        format_report_age(
            health_data.get(
                "latest_success_age_hours"
            )
        ),
    )

    col4.metric(
        "Consecutive Failures",
        health_data.get(
            "consecutive_failures",
            "Unavailable",
        ),
    )

    # --------------------------------------
    # 3. Health details
    # --------------------------------------

    st.write(
        "**Latest execution status:**",
        health_data.get(
            "latest_execution_status",
            "Unavailable",
        ),
    )

    st.write(
        "**Report freshness threshold:**",
        f"{health_data.get('report_age_threshold_hours', 'N/A')} hours",
    )

    st.write(
        "**Health checked at (UTC):**",
        health_data.get(
            "checked_at_utc",
            "Unavailable",
        ),
    )

    # --------------------------------------
    # 4. Detected issues
    # --------------------------------------

    issues = health_data.get(
        "issues",
        [],
    )

    if issues:

        st.subheader("Detected Issues")

        for issue in issues:
            st.warning(issue)

    else:

        st.write(
            "No operational issues detected "
            "by the configured health checks."
        )

    # --------------------------------------
    # 5. Latest successful report
    # --------------------------------------

    with st.expander(
        "Latest Successful Report Details"
    ):

        st.write(
            "**Execution ID:**",
            format_execution_id(
                health_data.get(
                    "latest_success_id"
                )
            ),
        )

        st.write(
            "**Report path:**",
            health_data.get(
                "latest_success_report"
            )
            or "Unavailable",
        )

        st.write(
            "**Latest execution error:**",
            health_data.get(
                "latest_execution_error"
            )
            or "None",
        )

    # --------------------------------------
    # 6. Raw health evaluation
    # --------------------------------------

    with st.expander(
        "Raw Health Evaluation"
    ):

        st.json(health_data)

    # --------------------------------------
    # 7. Monitoring limitations
    # --------------------------------------

    st.info(
        "Health is based on execution history and "
        "report freshness, not live electricity data. "
        "It does not independently verify whether "
        "the next macOS scheduled execution will run."
    )
