
"""
INNEVA.E - RELIABLE REPORT AUTOMATION
Module 15 - Checkpoint 15.7B

Features:
- Executes the local energy agent
- Writes report and metadata to temporary files
- Publishes completed files
- Cleans up incomplete publications
- Logs successful and failed executions in SQLite
- Returns a nonzero exit code on failure

Note:
Filesystem publication and SQLite logging are not
a fully atomic transaction.
"""

import argparse
import json
import re
import sys
import tempfile

from datetime import datetime, timezone
from pathlib import Path


# ============================================
# PROJECT CONFIGURATION
# ============================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

AGENTS_DIRECTORY = PROJECT_ROOT / "src" / "agents"

REPORTS_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
    / "energy_intelligence"
)

sys.path.insert(0, str(AGENTS_DIRECTORY))

from local_energy_agent import run_agent
from automation_logger import log_execution


AUTOMATION_NAME = "energy_intelligence_report"

REPORT_REQUEST = (
    "Analyze the historical electricity market, "
    "check the data quality, and generate a "
    "one-hour-ahead demand forecast. "
    "Explain the most important findings "
    "and limitations."
)


# ============================================
# TEMPORARY FILE HANDLING
# ============================================

def write_temporary_file(directory, content, suffix):

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=suffix,
        prefix=".innevae_tmp_",
        dir=directory,
        delete=False,
    ) as file:

        file.write(content)
        file.flush()

        return Path(file.name)


# ============================================
# REPORT AUTOMATION
# ============================================

def generate_report(mode="development_90d"):

    if mode not in {"development_90d", "full_history"}:
        raise ValueError(f"Unsupported dataset mode: {mode}")

    started_at = datetime.now(timezone.utc)

    print("=" * 65)
    print("INNEVA.E - RELIABLE REPORT AUTOMATION")
    print("=" * 65)

    print(f"Started: {started_at.isoformat()}")

    result = None

    temporary_files = []
    published_files = []

    report_path = None
    metadata_path = None

    status = "failed"
    error_message = None
    execution_id = None

    try:

        REPORTS_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ------------------------------------
        # 1. Execute AI agent
        # ------------------------------------

        result = run_agent(REPORT_REQUEST, mode=mode)

        if not result:
            raise RuntimeError(
                "The AI agent returned no result."
            )

        if result.get("status") != "checks_passed":
            raise RuntimeError(
                "The AI agent failed its validation checks."
            )

        # Require a successful validator result before writing anything.
        validation = result.get("validation")
        if not isinstance(validation, dict) or validation.get("status") != "pass":
            raise RuntimeError("Agent did not return passing validation evidence.")
        if validation.get("errors"):
            raise RuntimeError("Agent validation contains errors.")
        required_tools = {"get_energy_overview", "get_data_quality", "forecast_next_hour"}
        if not required_tools.issubset(set(result.get("executed_tools", []))):
            raise RuntimeError("Required analytical tools were not all executed.")
        report_text = result.get("report")
        if not isinstance(report_text, str) or not report_text.strip():
            raise RuntimeError("Agent returned an empty report.")

        # Read the verified-facts block rather than guessing the data period.
        # Reject publication if expected provenance fields are absent.
        def fact(pattern):
            match = re.search(pattern, report_text, flags=re.MULTILINE)
            if match is None:
                raise RuntimeError(f"Missing report provenance: {pattern}")
            return match.group(1).strip()

        dataset_mode = fact(r"^Dataset mode:\s*(.+)$")
        dataset_period_start_utc = fact(r"^Period start:\s*(.+)$")
        dataset_period_end_utc = fact(r"^Period end:\s*(.+)$")
        dataset_observation_count = int(
            fact(r"^Historical hourly observations:\s*([\d,]+)$").replace(",", "")
        )
        source_column_count = int(fact(r"^Original source columns:\s*(\d+)$"))
        if dataset_mode != mode:
            raise RuntimeError(
                f"Report mode mismatch: requested {mode}, received {dataset_mode}"
            )
        expected_count = {"development_90d": 2160, "full_history": 24096}[mode]
        if dataset_observation_count != expected_count or source_column_count != 37:
            raise RuntimeError(
                f"Unexpected dataset shape: {dataset_observation_count} rows, "
                f"{source_column_count} columns for {mode}"
            )

        # ------------------------------------
        # 2. Prepare report and metadata
        # ------------------------------------

        generated_at = datetime.now(timezone.utc)

        timestamp = generated_at.strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        report_path = (
            REPORTS_DIRECTORY
            / f"energy_report_{timestamp}.md"
        )

        metadata_path = (
            REPORTS_DIRECTORY
            / f"energy_report_{timestamp}.json"
        )

        report_content = (
            "# INNEVA.E Energy Intelligence Report\n\n"
            f"Generated at: {generated_at.isoformat()}\n\n"
            "Validation: Automated checks passed; "
            "AI interpretation is not fully verified.\n\n"
            "---\n\n"
            + report_text
            + "\n"
        )

        metadata = {
            "automation": AUTOMATION_NAME,
            "status": "checks_passed",
            "started_at_utc": started_at.isoformat(),
            "generated_at_utc": generated_at.isoformat(),
            "report_filename": report_path.name,
            "model": "qwen2.5:1.5b",
            "executed_tools": result.get(
                "executed_tools", []
            ),
            "validation": result.get(
                "validation", {}
            ),
            "data_type": "historical_snapshot",
            "dataset_mode": dataset_mode,
            "dataset_period_start_utc": dataset_period_start_utc,
            "dataset_period_end_utc": dataset_period_end_utc,
            "dataset_observation_count": dataset_observation_count,
            "source_column_count": source_column_count,
            "report_generation_attempts": result.get("attempts"),
            "interpretation_caveat": (
                "Automated checks passed; AI interpretation is not fully verified."
            ),
        }

        # ------------------------------------
        # 3. Write temporary files
        # ------------------------------------

        temporary_report = write_temporary_file(
            REPORTS_DIRECTORY,
            report_content,
            ".md.tmp",
        )

        temporary_files.append(temporary_report)

        temporary_metadata = write_temporary_file(
            REPORTS_DIRECTORY,
            json.dumps(metadata, indent=2),
            ".json.tmp",
        )

        temporary_files.append(temporary_metadata)

        # ------------------------------------
        # 4. Publish files
        # ------------------------------------

        temporary_report.replace(report_path)
        published_files.append(report_path)

        temporary_metadata.replace(metadata_path)
        published_files.append(metadata_path)

        # ------------------------------------
        # 5. Log successful execution
        # ------------------------------------

        completed_at = datetime.now(timezone.utc)

        execution_id = log_execution(
            automation_name=AUTOMATION_NAME,
            started_at_utc=started_at.isoformat(),
            finished_at_utc=completed_at.isoformat(),
            status="success",
            report_path=str(report_path),
            metadata_path=str(metadata_path),
            executed_tools=result.get(
                "executed_tools", []
            ),
            validation=result.get(
                "validation", {}
            ),
        )

        status = "success"

    except Exception as error:

        error_message = str(error)

        print("\nAUTOMATION ERROR:")
        print(error_message)

        # ------------------------------------
        # 6. Clean up incomplete publications
        # ------------------------------------

        for path in temporary_files + published_files:

            try:
                path.unlink(missing_ok=True)

            except OSError as cleanup_error:
                print(
                    "Cleanup warning:",
                    cleanup_error,
                )

        # ------------------------------------
        # 7. Record failure
        # ------------------------------------

        try:

            execution_id = log_execution(
                automation_name=AUTOMATION_NAME,
                started_at_utc=started_at.isoformat(),
                finished_at_utc=(
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
                status="failed",
                executed_tools=(
                    result.get("executed_tools", [])
                    if result
                    else []
                ),
                validation=(
                    result.get("validation", {})
                    if result
                    else {}
                ),
                error_message=error_message,
            )

        except Exception as logging_error:

            print(
                "Failed to record execution:",
                logging_error,
            )

    # ----------------------------------------
    # 8. Execution summary
    # ----------------------------------------

    completed_at = datetime.now(timezone.utc)

    duration = (
        completed_at - started_at
    ).total_seconds()

    print("\nAUTOMATION EXECUTION SUMMARY")
    print("=" * 65)

    print(f"Status: {status}")
    print(f"Execution ID: {execution_id}")
    print(f"Duration: {duration:.2f} seconds")

    if status == "success":

        print(f"Markdown report: {report_path}")
        print(f"Metadata file: {metadata_path}")

    else:

        print(f"Error: {error_message}")

    return {
        "status": status,
        "execution_id": execution_id,
        "duration_seconds": round(duration, 2),
        "report_path": (
            str(report_path)
            if status == "success"
            else None
        ),
        "metadata_path": (
            str(metadata_path)
            if status == "success"
            else None
        ),
    }


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Generate a validated historical energy report")
    parser.add_argument(
        "--mode", choices=("development_90d", "full_history"),
        default="development_90d",
        help="Canonical energy dataset window (default: development_90d)",
    )
    args = parser.parse_args()
    outcome = generate_report(mode=args.mode)

    if outcome["status"] != "success":
        sys.exit(1)
