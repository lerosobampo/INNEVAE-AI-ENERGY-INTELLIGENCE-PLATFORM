
"""
INNEVA.E - LOCAL AI AGENT MODEL BENCHMARK
Checkpoint 17.9D

Purpose:
    Compare local Ollama models using the same
    energy intelligence agent and datasets.

Supported models:
    - qwen2.5:1.5b
    - qwen2.5:3b

Supported dataset modes:
    - development_90d
    - full_history

Evaluation metrics:
    - Final validation success rate
    - First-attempt success rate
    - Retry recovery rate
    - Execution duration
    - Failed validation checks
    - Required tool execution

Outputs:
    - JSON evaluation report
    - Markdown evaluation summary
    - Per-run diagnostic logs

The script does not modify the agent or publish
operational energy intelligence reports.
"""

import argparse
import contextlib
import io
import json
import statistics
import sys
import time

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

AGENTS_DIRECTORY = PROJECT_ROOT / "src" / "agents"

EVALUATION_DIRECTORY = (
    PROJECT_ROOT / "reports" / "evaluation"
)

if str(AGENTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIRECTORY))


from local_energy_agent import run_agent


SUPPORTED_MODELS = (
    "qwen2.5:1.5b",
    "qwen2.5:3b",
)

DATASET_MODES = (
    "development_90d",
    "full_history",
)

REQUIRED_TOOLS = {
    "get_energy_overview",
    "get_data_quality",
    "forecast_next_hour",
}

REPORT_REQUEST = (
    "Analyze the historical electricity market, "
    "check the data quality, and generate a "
    "one-hour-ahead demand forecast. "
    "Explain the most important findings "
    "and limitations."
)


# ============================================================
# 2. HELPER FUNCTIONS
# ============================================================

def utc_now():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def percentage(numerator, denominator):
    """Calculate percentage safely."""

    if denominator == 0:
        return None

    return round(
        numerator / denominator * 100,
        2,
    )


def average(values):
    """Calculate arithmetic mean."""

    if not values:
        return None

    return round(
        statistics.mean(values),
        3,
    )


def median(values):
    """Calculate median."""

    if not values:
        return None

    return round(
        statistics.median(values),
        3,
    )


def format_metric(value, suffix=""):
    """Format optional metrics."""

    if value is None:
        return "N/A"

    return f"{value}{suffix}"


def save_json(path, data):
    """Save JSON report."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def model_slug(model):
    """
    Convert model name to filesystem-safe text.

    Example:
        qwen2.5:3b -> qwen2_5_3b
    """

    return (
        model.replace(".", "_")
        .replace(":", "_")
        .replace("/", "_")
    )


# ============================================================
# 3. EXECUTE ONE AGENT EVALUATION
# ============================================================

def evaluate_single_run(
    dataset_mode,
    run_number,
    run_id,
    model,
):
    """
    Execute one complete AI agent workflow.

    Collect:
        - Selected model
        - Agent status
        - Number of attempts
        - Validation checks
        - Tool execution
        - Execution duration
        - Diagnostic output
    """

    print()
    print("=" * 65)

    print(
        f"MODEL: {model} | "
        f"DATASET: {dataset_mode} | "
        f"RUN: {run_number}"
    )

    print("=" * 65)

    started_at = utc_now()

    start_timer = time.perf_counter()

    diagnostic_output = io.StringIO()

    result = None
    execution_error = None

    # --------------------------------------------------------
    # Execute the agent
    # --------------------------------------------------------

    try:

        with contextlib.redirect_stdout(
            diagnostic_output
        ):

            result = run_agent(
                REPORT_REQUEST,
                mode=dataset_mode,
                model=model,
            )

    except Exception as error:

        execution_error = (
            f"{type(error).__name__}: {error}"
        )

    duration = round(
        time.perf_counter() - start_timer,
        3,
    )

    completed_at = utc_now()

    # --------------------------------------------------------
    # Save diagnostic log
    # --------------------------------------------------------

    log_directory = (
        EVALUATION_DIRECTORY
        / "agent_runs"
        / run_id
    )

    log_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_path = (
        log_directory
        / (
            f"{model_slug(model)}_"
            f"{dataset_mode}_"
            f"run_{run_number:02d}.log"
        )
    )

    log_content = diagnostic_output.getvalue()

    if execution_error:

        log_content += (
            "\n\nEVALUATION EXECUTION ERROR:\n"
            + execution_error
            + "\n"
        )

    log_path.write_text(
        log_content,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Normalize agent results
    # --------------------------------------------------------

    if not isinstance(result, dict):
        result = {}

    validation = result.get(
        "validation",
        {},
    )

    if not isinstance(validation, dict):
        validation = {}

    checks = validation.get(
        "checks",
        {},
    )

    if not isinstance(checks, dict):
        checks = {}

    errors = validation.get(
        "errors",
        [],
    )

    if not isinstance(errors, list):
        errors = [str(errors)]

    errors = list(errors)

    executed_tools = result.get(
        "executed_tools",
        [],
    )

    if not isinstance(executed_tools, list):
        executed_tools = []

    attempts = result.get(
        "attempts",
    )

    if (
        type(attempts) is not int
        or attempts < 1
    ):
        attempts = None

    # --------------------------------------------------------
    # Verify required tools
    # --------------------------------------------------------

    all_required_tools = (
        REQUIRED_TOOLS.issubset(
            set(executed_tools)
        )
    )

    # --------------------------------------------------------
    # Verify validation results
    # --------------------------------------------------------

    validation_passed = (
        validation.get("status") == "pass"
        and not errors
        and bool(checks)
        and all(
            value is True
            for value in checks.values()
        )
    )

    final_success = (
        result.get("status") == "checks_passed"
        and validation_passed
        and all_required_tools
        and isinstance(
            result.get("report"),
            str,
        )
        and bool(
            result.get("report", "").strip()
        )
    )

    first_attempt_success = (
        final_success
        and attempts == 1
    )

    retry_attempted = (
        attempts is not None
        and attempts > 1
    )

    retry_recovered = (
        final_success
        and retry_attempted
    )

    failed_checks = [
        name
        for name, passed in checks.items()
        if passed is not True
    ]

    # --------------------------------------------------------
    # Collect execution errors
    # --------------------------------------------------------

    if execution_error:
        errors.append(execution_error)

    agent_error = result.get("error")

    if agent_error:
        errors.append(str(agent_error))

    if not final_success and not errors:

        errors.append(
            "Agent did not satisfy all final "
            "evaluation success conditions."
        )

    # --------------------------------------------------------
    # Build individual run record
    # --------------------------------------------------------

    record = {
        "model": model,
        "dataset_mode": dataset_mode,
        "run_number": run_number,

        "started_at_utc": (
            started_at.isoformat()
        ),

        "completed_at_utc": (
            completed_at.isoformat()
        ),

        "duration_seconds": duration,

        "agent_status": result.get(
            "status"
        ),

        "validation_status": validation.get(
            "status"
        ),

        "final_success": final_success,

        "first_attempt_success": (
            first_attempt_success
        ),

        "retry_attempted": retry_attempted,

        "retry_recovered": retry_recovered,

        "attempts": attempts,

        "all_required_tools_executed": (
            all_required_tools
        ),

        "executed_tools": executed_tools,

        "validation_check_count": len(
            checks
        ),

        "failed_checks": failed_checks,

        "errors": errors,

        "diagnostic_log": str(
            log_path.relative_to(
                PROJECT_ROOT
            )
        ),
    }

    # --------------------------------------------------------
    # Display execution result
    # --------------------------------------------------------

    status = (
        "PASS"
        if final_success
        else "FAIL"
    )

    print(f"Status: {status}")

    print(
        f"Duration: {duration:.2f} seconds"
    )

    print(
        "Attempts: "
        + (
            str(attempts)
            if attempts is not None
            else "Unknown"
        )
    )

    print(
        "Validation: "
        + str(
            validation.get(
                "status",
                "unavailable",
            )
        )
    )

    print(
        "Required tools executed: "
        f"{all_required_tools}"
    )

    print(
        f"Validation checks: {len(checks)}"
    )

    if errors:

        print("Errors:")

        for error in errors:
            print(f"  - {error}")

    print(
        f"Diagnostic log: {log_path}"
    )

    return record


# ============================================================
# 4. AGGREGATE EVALUATION METRICS
# ============================================================

def summarize_runs(records):
    """
    Calculate reliability metrics for completed runs.
    """

    total_runs = len(records)

    successful_runs = sum(
        record["final_success"]
        for record in records
    )

    first_attempt_successes = sum(
        record["first_attempt_success"]
        for record in records
    )

    retry_attempts = sum(
        record["retry_attempted"]
        for record in records
    )

    retry_recoveries = sum(
        record["retry_recovered"]
        for record in records
    )

    durations = [
        record["duration_seconds"]
        for record in records
    ]

    successful_durations = [
        record["duration_seconds"]
        for record in records
        if record["final_success"]
    ]

    failed_check_counts = Counter()

    failure_reasons = Counter()

    for record in records:

        failed_check_counts.update(
            record["failed_checks"]
        )

        if not record["final_success"]:

            failure_reasons.update(
                record["errors"]
            )

    return {
        "total_runs": total_runs,

        "successful_runs": successful_runs,

        "failed_runs": (
            total_runs - successful_runs
        ),

        "final_success_rate_pct": percentage(
            successful_runs,
            total_runs,
        ),

        "first_attempt_successes": (
            first_attempt_successes
        ),

        "first_attempt_success_rate_pct": percentage(
            first_attempt_successes,
            total_runs,
        ),

        "retry_attempts": retry_attempts,

        "retry_recoveries": retry_recoveries,

        "retry_recovery_rate_pct": percentage(
            retry_recoveries,
            retry_attempts,
        ),

        "average_duration_seconds": average(
            durations
        ),

        "median_duration_seconds": median(
            durations
        ),

        "average_success_duration_seconds": average(
            successful_durations
        ),

        "minimum_duration_seconds": (
            min(durations)
            if durations
            else None
        ),

        "maximum_duration_seconds": (
            max(durations)
            if durations
            else None
        ),

        "failed_checks": dict(
            failed_check_counts.most_common()
        ),

        "failure_reasons": dict(
            failure_reasons.most_common()
        ),
    }


# ============================================================
# 5. GENERATE MARKDOWN REPORT
# ============================================================

def create_markdown_report(evaluation):
    """
    Generate a readable Markdown evaluation report.
    """

    overall = evaluation[
        "overall_summary"
    ]

    summaries = evaluation[
        "dataset_summaries"
    ]

    short = summaries[
        "development_90d"
    ]

    full = summaries[
        "full_history"
    ]

    lines = [
        "# INNEVA.E Local AI Agent Benchmark",
        "",
        "## Experiment Configuration",
        "",
        (
            "- Evaluation ID: "
            f"{evaluation['evaluation_id']}"
        ),
        (
            "- Model: "
            f"{evaluation['model']}"
        ),
        (
            "- Generated at: "
            f"{evaluation['generated_at_utc']}"
        ),
        (
            "- Runs per dataset: "
            f"{evaluation['runs_per_mode']}"
        ),
        "- Agent workflow: Fixed three-tool execution",
        "- Data source: Canonical historical energy CSV",
        "",
        "## Overall Results",
        "",
    ]

    metrics = [
        (
            "Total executions",
            overall["total_runs"],
        ),
        (
            "Successful executions",
            overall["successful_runs"],
        ),
        (
            "Failed executions",
            overall["failed_runs"],
        ),
        (
            "Final success rate",
            format_metric(
                overall[
                    "final_success_rate_pct"
                ],
                "%",
            ),
        ),
        (
            "First-attempt success rate",
            format_metric(
                overall[
                    "first_attempt_success_rate_pct"
                ],
                "%",
            ),
        ),
        (
            "Retry recovery rate",
            format_metric(
                overall[
                    "retry_recovery_rate_pct"
                ],
                "%",
            ),
        ),
        (
            "Average execution time",
            format_metric(
                overall[
                    "average_duration_seconds"
                ],
                " seconds",
            ),
        ),
    ]

    for label, value in metrics:

        lines.append(
            f"- **{label}:** {value}"
        )

    lines.extend([
        "",
        "## Results by Dataset",
        "",
        (
            "| Metric | Latest 90 Days "
            "| Full History |"
        ),
        "|---|---:|---:|",
    ])

    table_rows = [
        (
            "Executions",
            "total_runs",
            "",
        ),
        (
            "Successful",
            "successful_runs",
            "",
        ),
        (
            "Failed",
            "failed_runs",
            "",
        ),
        (
            "Final success rate",
            "final_success_rate_pct",
            "%",
        ),
        (
            "First-attempt success rate",
            "first_attempt_success_rate_pct",
            "%",
        ),
        (
            "Retry recovery rate",
            "retry_recovery_rate_pct",
            "%",
        ),
        (
            "Average duration",
            "average_duration_seconds",
            " s",
        ),
    ]

    for label, key, suffix in table_rows:

        short_value = format_metric(
            short[key],
            suffix,
        )

        full_value = format_metric(
            full[key],
            suffix,
        )

        lines.append(
            f"| {label} | "
            f"{short_value} | "
            f"{full_value} |"
        )

    lines.extend([
        "",
        "## Individual Executions",
        "",
        (
            "| Model | Dataset | Run | "
            "Status | Attempts | Duration |"
        ),
        "|---|---|---:|---|---:|---:|",
    ])

    for record in evaluation["runs"]:

        status = (
            "PASS"
            if record["final_success"]
            else "FAIL"
        )

        attempts = (
            record["attempts"]
            if record["attempts"] is not None
            else "N/A"
        )

        lines.append(
            f"| {record['model']} | "
            f"{record['dataset_mode']} | "
            f"{record['run_number']} | "
            f"{status} | "
            f"{attempts} | "
            f"{record['duration_seconds']:.2f} s |"
        )

    lines.extend([
        "",
        "## Final Validation Failures",
        "",
    ])

    failed_checks = overall[
        "failed_checks"
    ]

    if failed_checks:

        for name, count in failed_checks.items():

            lines.append(
                f"- {name}: {count} occurrence(s)"
            )

    else:

        lines.append(
            "No failed checks were present in "
            "the final returned validations."
        )

    lines.extend([
        "",
        "## Interpretation and Limitations",
        "",
        (
            "- This benchmark measures whether "
            "the agent satisfies its automated "
            "validation rules."
        ),
        (
            "- Passing validation does not guarantee "
            "complete factual accuracy."
        ),
        (
            "- First-attempt success is inferred "
            "from the returned attempt count."
        ),
        (
            "- Only final validation failures are "
            "available as structured data."
        ),
        (
            "- Small samples are insufficient to "
            "establish production reliability."
        ),
        (
            "- Model performance depends on local "
            "hardware, memory, prompts and settings."
        ),
        (
            "- The evaluation does not publish "
            "operational energy intelligence reports."
        ),
        "",
    ])

    return "\n".join(lines)


# ============================================================
# 6. MAIN BENCHMARK WORKFLOW
# ============================================================

def run_evaluation(
    runs_per_mode,
    model,
):
    """
    Execute the benchmark for the selected local model.
    """

    if model not in SUPPORTED_MODELS:

        raise ValueError(
            f"Unsupported model: {model}"
        )

    EVALUATION_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = utc_now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    evaluation_id = (
        f"{timestamp}_{model_slug(model)}"
    )

    print()
    print("=" * 65)
    print("INNEVA.E - LOCAL AI AGENT MODEL BENCHMARK")
    print("=" * 65)

    print(
        f"Evaluation ID: {evaluation_id}"
    )

    print(f"Model: {model}")

    print(
        f"Runs per dataset: {runs_per_mode}"
    )

    print(
        f"Total planned runs: "
        f"{runs_per_mode * len(DATASET_MODES)}"
    )

    records = []

    # --------------------------------------------------------
    # Execute repeated agent runs
    # --------------------------------------------------------

    for dataset_mode in DATASET_MODES:

        for run_number in range(
            1,
            runs_per_mode + 1,
        ):

            record = evaluate_single_run(
                dataset_mode=dataset_mode,
                run_number=run_number,
                run_id=evaluation_id,
                model=model,
            )

            records.append(record)

    # --------------------------------------------------------
    # Calculate summaries
    # --------------------------------------------------------

    overall_summary = summarize_runs(
        records
    )

    dataset_summaries = {}

    for dataset_mode in DATASET_MODES:

        mode_records = [
            record
            for record in records
            if record["dataset_mode"] == dataset_mode
        ]

        dataset_summaries[dataset_mode] = (
            summarize_runs(mode_records)
        )

    # --------------------------------------------------------
    # Build evaluation result
    # --------------------------------------------------------

    evaluation = {
        "evaluation_id": evaluation_id,

        "generated_at_utc": (
            utc_now().isoformat()
        ),

        "model": model,

        "runs_per_mode": runs_per_mode,

        "total_planned_runs": (
            runs_per_mode * len(DATASET_MODES)
        ),

        "overall_summary": overall_summary,

        "dataset_summaries": dataset_summaries,

        "runs": records,
    }

    # --------------------------------------------------------
    # Save JSON and Markdown reports
    # --------------------------------------------------------

    json_path = (
        EVALUATION_DIRECTORY
        / f"agent_evaluation_{evaluation_id}.json"
    )

    markdown_path = (
        EVALUATION_DIRECTORY
        / f"agent_evaluation_{evaluation_id}.md"
    )

    save_json(
        json_path,
        evaluation,
    )

    markdown_report = create_markdown_report(
        evaluation
    )

    markdown_path.write_text(
        markdown_report,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Print final results
    # --------------------------------------------------------

    print()
    print("=" * 65)
    print("FINAL EVALUATION RESULTS")
    print("=" * 65)

    print(f"Model: {model}")

    print(
        f"Total runs: "
        f"{overall_summary['total_runs']}"
    )

    print(
        f"Successful runs: "
        f"{overall_summary['successful_runs']}"
    )

    print(
        f"Failed runs: "
        f"{overall_summary['failed_runs']}"
    )

    print(
        "Final success rate: "
        + format_metric(
            overall_summary[
                "final_success_rate_pct"
            ],
            "%",
        )
    )

    print(
        "First-attempt success rate: "
        + format_metric(
            overall_summary[
                "first_attempt_success_rate_pct"
            ],
            "%",
        )
    )

    print(
        "Retry recovery rate: "
        + format_metric(
            overall_summary[
                "retry_recovery_rate_pct"
            ],
            "%",
        )
    )

    print(
        "Average execution duration: "
        + format_metric(
            overall_summary[
                "average_duration_seconds"
            ],
            " seconds",
        )
    )

    print()
    print("REPORT FILES")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")

    return evaluation


# ============================================================
# 7. COMMAND-LINE INTERFACE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Benchmark a local Ollama model "
            "using the INNEVA.E energy agent."
        )
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help=(
            "Number of executions per dataset mode."
        ),
    )

    parser.add_argument(
        "--model",
        choices=SUPPORTED_MODELS,
        default="qwen2.5:1.5b",
        help="Local Ollama model to evaluate.",
    )

    args = parser.parse_args()

    if args.runs < 1:

        parser.error(
            "--runs must be at least 1."
        )

    run_evaluation(
        runs_per_mode=args.runs,
        model=args.model,
    )


if __name__ == "__main__":
    main()
