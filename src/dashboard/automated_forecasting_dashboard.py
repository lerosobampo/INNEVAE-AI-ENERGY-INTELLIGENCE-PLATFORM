"""INNEVA.E — Automated Forecasting Dashboard.

Read-only visualization of development forecasting and pipeline history.
Does not run ingestion or generate forecasts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_DIR = ROOT / "src" / "automation"
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

import forecast_update_detector as detector

PIPELINE_HISTORY = ROOT / "reports" / "energy_pipeline" / "pipeline_history.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    records.append(item)
            except json.JSONDecodeError:
                continue
    return records


def render_automated_forecasting_dashboard() -> None:
    st.header("Automated Forecasting")
    st.caption(
        "Historical development forecasts, execution history, and integrity "
        "monitoring. These are not live operational predictions."
    )
    if st.button("Refresh monitoring data", key="refresh_automated_forecasting"):
        st.rerun()

    try:
        assessment = detector.detect_update(horizon="24h", method="auto")
    except Exception as error:
        st.error(f"Forecast monitoring failed: {error}")
        return

    forecasts = read_jsonl(detector.MANIFEST_FILE)
    pipeline_runs = read_jsonl(PIPELINE_HISTORY)
    latest_pipeline = pipeline_runs[-1] if pipeline_runs else None
    status = assessment.get("status", "UNKNOWN")

    st.subheader("System Status")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Forecast integrity", status)
    c2.metric("Latest pipeline", latest_pipeline.get("status", "UNKNOWN") if latest_pipeline else "NOT RUN")
    c3.metric("Saved forecast runs", len(forecasts))
    c4.metric("Forecast horizon", "24 hours")

    if status == "UP_TO_DATE":
        st.success("Latest automated forecast verified against the development dataset.")
    elif status == "READY":
        st.info("A new forecast can be generated from the current development dataset.")
    elif status == "RECOVERY_REQUIRED":
        st.warning("Saved forecast is missing or invalid. Recovery is required.")
    else:
        st.error("Forecasting is blocked: " + str(assessment.get("reason", "Unknown reason")))

    st.divider()
    st.subheader("Dataset Provenance")
    dataset = assessment.get("dataset", {})
    if isinstance(dataset, dict) and dataset:
        c1, c2, c3 = st.columns(3)
        c1.metric("Development observations", f"{dataset.get('total_rows', 0):,}")
        c2.metric("Latest observation (UTC)", str(dataset.get("latest_observation_utc") or "Unknown")[:16])
        c3.metric("Forecast issue (UTC)", str(dataset.get("proposed_issue_time_utc") or "Unknown")[:16])
        with st.expander("Source dataset details"):
            st.json(dataset)
    st.caption("The protected production dataset is not modified by this dashboard.")

    st.divider()
    st.subheader("Latest Automated Forecast")
    previous = assessment.get("previous_forecast")
    if status == "UP_TO_DATE" and isinstance(previous, dict) and previous.get("output_file"):
        path = Path(previous["output_file"])
        try:
            df = pd.read_csv(path)
            df["forecast_time_utc"] = pd.to_datetime(df["forecast_time_utc"], utc=True)
            values = pd.to_numeric(df["predicted_demand_mw"], errors="raise")
            m1, m2, m3 = st.columns(3)
            m1.metric("Average demand", f"{values.mean():,.0f} MW")
            m2.metric("Minimum demand", f"{values.min():,.0f} MW")
            m3.metric("Maximum demand", f"{values.max():,.0f} MW")
            fig = px.line(
                df,
                x="forecast_time_utc",
                y="predicted_demand_mw",
                title="Automated Hourly Demand Forecast",
                labels={"forecast_time_utc": "Forecast time (UTC)", "predicted_demand_mw": "Demand (MW)"},
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("Hourly predictions"):
                st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download automated forecast",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="innevae_automated_forecast.csv",
                mime="text/csv",
            )
        except Exception as error:
            st.error(f"Unable to display saved forecast: {error}")
    else:
        st.info("No currently verified forecast is available for the development dataset.")

    st.divider()
    st.subheader("Forecast Execution History")
    if forecasts:
        history = pd.DataFrame(forecasts)
        columns = [
            "generated_at_utc", "forecast_id", "status", "horizon",
            "requested_method", "selected_method", "prediction_count", "forecast_type",
        ]
        st.dataframe(history[[c for c in columns if c in history.columns]].iloc[::-1], use_container_width=True, hide_index=True)
    else:
        st.info("No automated forecasts recorded.")

    st.divider()
    st.subheader("Pipeline Execution History")
    if pipeline_runs:
        history = pd.DataFrame(pipeline_runs)
        columns = [
            "started_at_utc", "status", "refresh_status",
            "forecast_assessment_status", "forecast_status", "forecast_id",
        ]
        st.dataframe(history[[c for c in columns if c in history.columns]].iloc[::-1], use_container_width=True, hide_index=True)
    else:
        st.info("No pipeline executions recorded.")
    st.caption("Development-only monitoring. Forecast generation and scheduling are managed separately.")
