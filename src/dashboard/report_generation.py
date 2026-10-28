
"""
INNEVA.E - DASHBOARD REPORT GENERATION
Module 16 - Checkpoint 16.4B

Runs the existing report automation from Streamlit.

Does not duplicate:
- AI agent logic
- Response validation
- Report publication
- SQLite execution logging
"""

import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]

AUTOMATION_DIRECTORY = (
    PROJECT_ROOT / "src" / "automation"
)

if str(AUTOMATION_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIRECTORY))

from generate_energy_report import generate_report


def execute_report_generation(mode="development_90d"):
    """
    Execute the existing automation and validate
    its returned execution summary.
    """

    if mode not in {"development_90d", "full_history"}:
        raise ValueError(f"Unsupported dataset mode: {mode}")

    result = generate_report(mode=mode)

    if not isinstance(result, dict):
        raise TypeError(
            "Automation must return a dictionary."
        )

    required_fields = {
        "status",
        "execution_id",
        "duration_seconds",
        "report_path",
        "metadata_path",
    }

    missing = required_fields - result.keys()

    if missing:
        raise ValueError(
            f"Missing automation fields: {sorted(missing)}"
        )

    if result["status"] != "success":
        raise RuntimeError(
            "Report automation failed. "
            f"Execution ID: {result['execution_id']}. "
            "Inspect the automation execution log."
        )

    if result["execution_id"] is None:
        raise ValueError(
            "Successful automation has no execution ID."
        )

    report_path = Path(result["report_path"])
    metadata_path = Path(result["metadata_path"])

    if not report_path.is_file():
        raise FileNotFoundError(report_path)

    if not metadata_path.is_file():
        raise FileNotFoundError(metadata_path)

    if report_path.stem != metadata_path.stem:
        raise ValueError(
            "Report and metadata filenames do not match."
        )

    return result


def render_report_generation():
    """
    Display a manually triggered AI report
    generation control.
    """

    st.subheader("Generate New AI Report")

    st.write(
        "Execute the existing INNEVA.E automation "
        "using the local Qwen2.5 model."
    )

    st.caption(
        "Reports use the canonical hourly energy CSV. Select the latest 90 days "
        "or the complete historical dataset; generation does not refresh source data."
    )

    mode_label = st.selectbox(
        "Report dataset", ["Latest 90 days", "Full history (2024 onward)"],
        key="standalone_ai_report_mode",
    )
    mode = ("development_90d" if mode_label == "Latest 90 days" else "full_history")

    if st.button(
        "Generate New AI Report",
        key="generate_new_ai_report",
        type="primary",
    ):

        st.session_state.pop(
            "innevae_last_generation",
            None,
        )

        try:
            with st.spinner(
                "Running energy tools, local AI model, "
                "validation, and report publication..."
            ):
                result = execute_report_generation(mode=mode)

            st.session_state[
                "innevae_last_generation"
            ] = result

            st.session_state[
                "selected_ai_report"
            ] = Path(
                result["report_path"]
            ).stem

            st.success(
                "AI report generated successfully."
            )

        except Exception as error:
            st.error(
                f"Report generation failed: {error}"
            )

    result = st.session_state.get(
        "innevae_last_generation"
    )

    if result:
        st.write(
            "**Execution ID:**",
            result["execution_id"],
        )

        st.write(
            "**Duration:**",
            f"{result['duration_seconds']:.2f} seconds",
        )

        st.write(
            "**Report file:**",
            result["report_path"],
        )

        st.caption(
            "The generated report will appear "
            "in the report explorer below."
        )
