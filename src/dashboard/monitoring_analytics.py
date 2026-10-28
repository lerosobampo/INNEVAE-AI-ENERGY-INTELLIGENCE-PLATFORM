
"""
INNEVA.E - MONITORING ANALYTICS
Module 16 - Checkpoint 16.5C

Analyzes historical automation executions.

Features:
- Success/failure distribution
- Execution duration
- Execution performance over time
- Recent success rate
- Read-only analytics

Uses existing monitoring_data.py.
"""

import pandas as pd
import plotly.express as px
import streamlit as st


# ==========================================
# DATA PREPARATION
# ==========================================

def prepare_monitoring_analytics(history):
    """
    Prepare execution records for analytics.

    Execution duration is calculated using
    the recorded start and finish timestamps.
    """

    required_columns = [
        "execution_id",
        "started_at_utc",
        "finished_at_utc",
        "status",
    ]

    missing = [
        column
        for column in required_columns
        if column not in history.columns
    ]

    if missing:
        raise ValueError(
            f"Missing monitoring columns: {missing}"
        )

    df = history.copy()

    df["started_at_utc"] = pd.to_datetime(
        df["started_at_utc"],
        utc=True,
        errors="coerce",
    )

    df["finished_at_utc"] = pd.to_datetime(
        df["finished_at_utc"],
        utc=True,
        errors="coerce",
    )

    df["duration_seconds"] = (
        df["finished_at_utc"]
        - df["started_at_utc"]
    ).dt.total_seconds()

    # Invalid or negative durations should not
    # be included in performance calculations.

    df.loc[
        df["duration_seconds"] < 0,
        "duration_seconds",
    ] = float("nan")

    df["execution_label"] = (
        "#"
        + df["execution_id"].astype(str)
    )

    df["successful"] = (
        df["status"] == "success"
    ).astype(int)

    df = df.sort_values(
        "execution_id"
    ).reset_index(drop=True)

    return df


# ==========================================
# PERFORMANCE METRICS
# ==========================================

def calculate_monitoring_metrics(df):

    total = len(df)

    successful = int(
        (df["status"] == "success").sum()
    )

    failed = int(
        (df["status"] == "failed").sum()
    )

    success_rate = (
        successful / total * 100
        if total
        else 0.0
    )

    completed = df[
        df["duration_seconds"].notna()
    ]

    average_duration = (
        completed["duration_seconds"].mean()
        if not completed.empty
        else None
    )

    recent = df.tail(5)

    recent_success_rate = (
        recent["successful"].mean() * 100
        if not recent.empty
        else 0.0
    )

    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "success_rate": success_rate,
        "average_duration_seconds": average_duration,
        "recent_success_rate": recent_success_rate,
    }


# ==========================================
# STREAMLIT VISUALIZATION
# ==========================================

def render_monitoring_analytics(history):

    st.subheader("Monitoring Analytics")

    st.caption(
        "Historical automation performance "
        "calculated from SQLite execution records."
    )

    if history.empty:
        st.info(
            "No execution records are available."
        )
        return

    try:
        df = prepare_monitoring_analytics(
            history
        )

        metrics = calculate_monitoring_metrics(
            df
        )

    except Exception as error:
        st.error(
            f"Unable to calculate monitoring analytics: {error}"
        )
        return

    # --------------------------------------
    # 1. Performance KPIs
    # --------------------------------------

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Overall Success Rate",
        f"{metrics['success_rate']:.1f}%",
    )

    average_duration = metrics[
        "average_duration_seconds"
    ]

    col2.metric(
        "Average Execution Time",
        (
            f"{average_duration:.1f} sec"
            if average_duration is not None
            else "Unavailable"
        ),
    )

    col3.metric(
        "Last 5 Success Rate",
        f"{metrics['recent_success_rate']:.1f}%",
    )

    st.divider()

    # --------------------------------------
    # 2. Execution status distribution
    # --------------------------------------

    st.markdown(
        "#### Execution Status Distribution"
    )

    status_counts = (
        df["status"]
        .value_counts()
        .reset_index()
    )

    status_counts.columns = [
        "status",
        "count",
    ]

    fig_status = px.bar(
        status_counts,
        x="status",
        y="count",
        color="status",
        title="Successful vs Failed Executions",
        labels={
            "status": "Execution Status",
            "count": "Number of Executions",
        },
    )

    st.plotly_chart(
        fig_status,
        use_container_width=True,
    )

    # --------------------------------------
    # 3. Execution duration
    # --------------------------------------

    st.markdown(
        "#### Execution Duration"
    )

    duration_data = df.dropna(
        subset=["duration_seconds"]
    )

    if duration_data.empty:

        st.warning(
            "No valid execution durations available."
        )

    else:

        fig_duration = px.line(
            duration_data,
            x="execution_label",
            y="duration_seconds",
            markers=True,
            title="Automation Execution Duration",
            labels={
                "execution_label": "Execution",
                "duration_seconds": "Duration (seconds)",
            },
            hover_data=[
                "status",
                "started_at_utc",
            ],
        )

        st.plotly_chart(
            fig_duration,
            use_container_width=True,
        )

    # --------------------------------------
    # 4. Cumulative success rate
    # --------------------------------------

    st.markdown(
        "#### Historical Success Rate"
    )

    df["cumulative_success_rate"] = (
        df["successful"]
        .expanding()
        .mean()
        * 100
    )

    fig_success = px.line(
        df,
        x="execution_label",
        y="cumulative_success_rate",
        markers=True,
        title="Cumulative Automation Success Rate",
        labels={
            "execution_label": "Execution",
            "cumulative_success_rate": "Success Rate (%)",
        },
    )

    fig_success.update_yaxes(
        range=[0, 100]
    )

    st.plotly_chart(
        fig_success,
        use_container_width=True,
    )

    # --------------------------------------
    # 5. Analytics data table
    # --------------------------------------

    with st.expander(
        "Monitoring Analytics Data"
    ):

        columns = [
            "execution_id",
            "status",
            "started_at_utc",
            "finished_at_utc",
            "duration_seconds",
            "cumulative_success_rate",
        ]

        st.dataframe(
            df[columns].sort_values(
                "execution_id",
                ascending=False,
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "Historical test executions are included. "
        "Success rates measure recorded automation "
        "outcomes, not electricity forecast accuracy."
    )
