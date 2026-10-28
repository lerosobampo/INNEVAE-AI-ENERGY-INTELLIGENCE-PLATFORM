"""INNEVA.E AI Intelligence — Checkpoint 17.8D (safe data-source transition).

Shows canonical energy dataset context; retains historical report explorer.
Runs validated 90-day report automation and verifies published metadata.
"""
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
FORECASTING = ROOT / "src" / "forecasting"
if str(FORECASTING) not in sys.path:
    sys.path.insert(0, str(FORECASTING))

from unified_data_loader import load_energy_history, dataset_profile
from report_loader import discover_reports, load_report, REPORT_DIRECTORY
from report_generation import execute_report_generation


def render_ai_intelligence_dashboard():
    st.header("AI Intelligence")
    st.caption("Canonical energy observations — original 37-column schema")

    mode_labels = {
        "Latest 90 days": "development_90d",
        "Full history (2024 onward)": "full_history",
    }
    selected = st.selectbox(
        "Dataset for AI analysis",
        list(mode_labels),
        key="ai_intelligence_dataset_mode",
    )
    mode = mode_labels[selected]

    try:
        df = load_energy_history(mode)
        profile = dataset_profile(df)
    except Exception as exc:
        st.error(f"Unable to load canonical energy data: {exc}")
        return

    a, b, c = st.columns(3)
    a.metric("Hourly observations", f"{profile['rows']:,}")
    b.metric("Original variables", str(profile["columns"]))
    c.metric("Missing price hours", str(profile["missing_price_hours"]))
    st.caption(
        f"UTC period: {df['hour_start_utc'].min():%Y-%m-%d %H:%M} "
        f"to {df['hour_start_utc'].max():%Y-%m-%d %H:%M} | "
        f"Missing offshore wind hours: {profile['missing_offshore_hours']}"
    )

    with st.expander("Inspect canonical variables and data quality"):
        st.write("Original variables (unchanged):")
        st.code(", ".join(df.columns))
        nulls = df.isna().sum()
        st.dataframe(
            nulls[nulls > 0].rename("missing_hours").to_frame(),
            use_container_width=True,
        )
        st.dataframe(df.tail(10), use_container_width=True)

    st.divider()
    st.subheader("AI Report Generation")
    st.caption(
        "Reports are generated from the canonical hourly CSV using the dataset "
        "selected above. The 90-day and full-history modes are both supported."
    )
    if st.button(
        "Generate New AI Report",
        key="generate_new_ai_report",
        type="primary",
    ):
        try:
            with st.spinner("Running verified tools, Qwen, validation, and publication..."):
                result = execute_report_generation(mode=mode)
                metadata_path = Path(result["metadata_path"])
                if not metadata_path.is_file():
                    raise FileNotFoundError(metadata_path)
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if (
                    metadata.get("validation", {}).get("status") != "pass"
                    or metadata.get("dataset_mode") != mode
                    or metadata.get("dataset_observation_count") != profile["rows"]
                    or metadata.get("source_column_count") != profile["columns"]
                ):
                    raise ValueError(
                        "Published metadata does not match the selected dataset "
                        "and passing report requirements. Inspect files manually."
                    )
            st.session_state["innevae_last_generation"] = result
            st.session_state["selected_ai_report"] = Path(result["report_path"]).stem
            st.success(f"Report published. Execution ID: {result['execution_id']}")
            st.rerun()
        except Exception as exc:
            st.error(f"Report generation or metadata verification failed: {exc}")
            st.warning("If publication succeeded before verification failed, inspect the report files before using them.")

    last = st.session_state.get("innevae_last_generation")
    if last:
        st.caption(
            f"Last successful dashboard execution: {last['execution_id']} | "
            f"{last['duration_seconds']:.2f} seconds | "
            f"{Path(last['report_path']).name}"
        )

    st.divider()
    st.subheader("Historical AI Report Explorer")
    st.caption(
        "Existing reports are historical artifacts. The dataset preview selection "
        "does not change saved reports; inspect each report's metadata for coverage."
    )
    if st.button("Refresh Report List", key="refresh_ai_reports"):
        st.rerun()

    try:
        reports = discover_reports()
    except Exception as exc:
        st.error(f"Unable to discover reports: {exc}")
        return

    if not reports:
        st.warning("No complete AI report pairs found.")
        st.code(str(REPORT_DIRECTORY))
        return

    st.metric("Available Report Pairs", len(reports))
    options = {r["report_id"]: r for r in reports}
    available = list(options)
    if st.session_state.get("selected_ai_report") not in available:
        st.session_state["selected_ai_report"] = available[0]
    report_id = st.selectbox(
        "Select an existing report", available, key="selected_ai_report"
    )

    try:
        report = load_report(options[report_id])
    except Exception as exc:
        st.error(f"Unable to load report: {exc}")
        return

    st.caption("Report file last modified (UTC): " + report["modified_at_utc"])
    markdown_tab, json_tab, metadata_tab = st.tabs(
        ["AI Report", "Structured JSON", "Report Metadata"]
    )
    with markdown_tab:
        st.markdown(report["markdown"])
        st.download_button(
            "Download Markdown", report["markdown"],
            file_name=report["report_id"] + ".md",
            mime="text/markdown", key="download_ai_markdown",
        )
    with json_tab:
        st.json(report["json"])
        st.download_button(
            "Download JSON",
            json.dumps(report["json"], indent=2, ensure_ascii=False),
            file_name=report["report_id"] + ".json",
            mime="application/json", key="download_ai_json",
        )
    with metadata_tab:
        st.write("**Report identifier:**", report["report_id"])
        st.write("**Markdown file:**", str(report["markdown_path"]))
        st.write("**JSON file:**", str(report["json_path"]))
        st.write("**File modified at (UTC):**", report["modified_at_utc"])
        st.write("**Model:**", report["json"].get("model", "Not specified"))
        st.write("**Data type:**", report["json"].get("data_type", "Not specified"))
        st.write("**Validation status:**", report["json"].get("validation", {}).get("status", "Not specified"))
        st.write("**Dataset mode:**", report["json"].get("dataset_mode", "Not specified"))
        st.write("**Observation count:**", report["json"].get("dataset_observation_count", "Not specified"))
        st.write("**Source columns:**", report["json"].get("source_column_count", "Not specified"))
        st.write("**Executed tools:**", report["json"].get("executed_tools", []))
        st.caption("File modification time is not necessarily the AI execution timestamp.")

    st.divider()
    st.warning(
        "AI-generated interpretations require review before operational use. "
        "Automated checks do not guarantee factual accuracy."
    )
