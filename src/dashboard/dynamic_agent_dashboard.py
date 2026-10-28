"""INNEVA.E — Checkpoint 18.7.2: resilient local dynamic-agent dashboard.

Standalone Streamlit page or imported via render_dynamic_agent_dashboard().
Existing agent, validators and other dashboard modules are unchanged.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / "src" / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

MODE_LABELS = {
    "90-day development dataset": "development_90d",
    "Full historical dataset": "full_history",
}
SAMPLE_QUESTIONS = [
    "What was the average electricity demand?",
    "Identify missing observations in the dataset.",
    "Generate a one-hour-ahead historical electricity demand forecast.",
    "Identify missing data and generate a one-hour-ahead historical electricity demand forecast.",
    "Analyze average electricity demand, identify missing data, and generate a one-hour-ahead historical forecast.",
]
PREFIX = "innevae_dynamic_"


def _classify_exception(exc: Exception) -> tuple[str, str]:
    """Return actionable, non-sensitive guidance without claiming a specific cause."""
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if any(term in message for term in ("connection refused", "failed to connect", "could not connect", "connection error", "ollama server")) or "connecterror" in name:
        return ("Local AI service unavailable", "Check that Ollama is running and the qwen2.5:3b model is installed, then retry.")
    if "timeout" in name or "timed out" in message:
        return ("Request timed out", "The local model did not respond in time. Check Ollama and retry a simpler question.")
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return ("Project dependency unavailable", "Verify your virtual environment and that src/agents/dynamic_energy_agent.py exists.")
    return ("Agent execution error", "The request raised an exception. Inspect the terminal for details; the previous validated result remains available.")


def _valid_result(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("status") == "completed"
        and isinstance(result.get("validation"), dict)
        and result["validation"].get("status") == "pass"
        and isinstance(result.get("response"), str)
        and bool(result["response"].strip())
    )


def _render_result(record: dict, *, previous: bool = False) -> None:
    result = record["result"]
    validation = result.get("validation") or {}
    status = result.get("status", "unknown")
    valid = _valid_result(result)
    heading = "Previous validated analysis" if previous else "Latest analysis result"
    st.subheader(heading)
    st.caption(f"Question: {record['question']} · Dataset: {record['mode']} · Run: {record['at']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Execution", f"{record['elapsed']:.1f} s")
    c2.metric("Executed tools", len(result.get("selected_tools") or []))
    c3.metric("Validation", "PASS" if valid else "NOT PASSED")

    if valid:
        st.success("Answer passed the configured automated checks (not a guarantee of factual accuracy).")
        st.write(result["response"])
    else:
        st.error(f"No validated answer available. Agent status: {status}.")
        if result.get("error"):
            st.write(str(result["error"]))
        if validation.get("errors"):
            st.write("Validation errors:", validation["errors"])
        st.caption("An unvalidated narrative is never displayed as an approved answer.")

    with st.expander("Tool selection and authorization", expanded=not previous):
        st.write("**Proposed by model:**", result.get("tools_proposed_by_model", []))
        st.write("**Executed:**", result.get("selected_tools", []))
        st.write("**Rejected by authorizer:**", result.get("tools_rejected_by_authorizer", []))
        st.write("**Added by verifier:**", result.get("tools_added_by_verifier", []))
        st.write("**Explicit intent:**", result.get("required_tools_inferred", []))

    with st.expander("Validation checks"):
        checks = validation.get("checks") or {}
        if checks:
            st.dataframe(
                [{"Check": key, "Passed": bool(value)} for key, value in checks.items()],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No validation checks available for this result.")
        if validation.get("warning"):
            st.caption(validation["warning"])

    with st.expander("Historical tool results (JSON)"):
        st.json(result.get("tool_results") or {})
    with st.expander("Agent execution log"):
        st.code(record.get("log", "") or "No console log was captured.", language="text")

    st.download_button(
        "Download execution result (JSON)",
        data=json.dumps(result, indent=2, ensure_ascii=False, default=str),
        file_name="innevae_dynamic_agent_previous.json" if previous else "innevae_dynamic_agent_result.json",
        mime="application/json",
        key="innevae_download_previous" if previous else "innevae_download_latest",
    )


def render_dynamic_agent_dashboard() -> None:
    """Render a resilient agent page, compatible with the existing app.py."""
    st.title("Dynamic AI Energy Analyst")
    st.caption("INNEVA.E · Checkpoint 18.7.2 · Local Ollama · Historical data only")
    st.info(
        "This assistant analyzes historical energy records. Forecasts are historical "
        "persistence scenarios, not live market forecasts."
    )

    with st.form("dynamic_agent_question_form"):
        dataset_label = st.selectbox("Dataset", options=list(MODE_LABELS))
        question = st.text_area(
            "Ask an energy analytics question",
            placeholder="e.g. Identify missing data and forecast next-hour demand.",
            height=110,
        )
        example = st.selectbox("Or choose an example", ["(Use my question)"] + SAMPLE_QUESTIONS)
        submitted = st.form_submit_button("Run validated analysis", type="primary")

    if submitted:
        actual_question = question.strip() or (example if example != "(Use my question)" else "")
        if not actual_question:
            st.warning("Enter a question or select an example before running the agent.")
        else:
            started = time.perf_counter()
            log_buffer = io.StringIO()
            try:
                from dynamic_energy_agent import run_dynamic_agent

                with st.status("Running local AI analysis…", expanded=True) as progress:
                    st.write("Request submitted to the local agent.")
                    st.write("Tool selection, execution and response validation may take a minute or longer.")
                    with contextlib.redirect_stdout(log_buffer):
                        result = run_dynamic_agent(
                            actual_question,
                            mode=MODE_LABELS[dataset_label],
                            model="qwen2.5:3b",
                        )
                    progress.update(label="Agent execution finished", state="complete", expanded=False)

                record = {
                    "result": result,
                    "elapsed": time.perf_counter() - started,
                    "log": log_buffer.getvalue(),
                    "question": actual_question,
                    "mode": MODE_LABELS[dataset_label],
                    "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
                st.session_state[PREFIX + "latest"] = record
                if _valid_result(result):
                    st.session_state[PREFIX + "last_valid"] = record
                    st.session_state.pop(PREFIX + "last_error", None)
                else:
                    st.session_state[PREFIX + "last_error"] = None
            except Exception as exc:
                title, guidance = _classify_exception(exc)
                st.session_state[PREFIX + "last_error"] = (title, guidance)
                st.session_state[PREFIX + "latest"] = None
                # Details stay in terminal, rather than exposing paths or sensitive diagnostics in the UI.
                print(f"[Dynamic Agent UI] {type(exc).__name__}: {exc}", file=sys.stderr)

    issue = st.session_state.get(PREFIX + "last_error")
    if issue:
        st.error(issue[0])
        st.info(issue[1])

    latest = st.session_state.get(PREFIX + "latest")
    last_valid = st.session_state.get(PREFIX + "last_valid")
    if latest:
        st.divider()
        _render_result(latest)
    elif not last_valid:
        st.caption("Run a question to see the verified answer and execution details.")

    if last_valid and (not latest or latest is not last_valid):
        st.divider()
        st.info("Your most recent validated analysis is preserved below. It is not the result of the latest attempt.")
        _render_result(last_valid, previous=True)


if __name__ == "__main__":
    st.set_page_config(page_title="INNEVA.E | Dynamic AI Analyst", page_icon="⚡", layout="wide")
    render_dynamic_agent_dashboard()
