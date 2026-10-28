"""INNEVA.E — Checkpoint 18.4: local dynamic-agent evaluation.

Run from the project root:
    python3 src/evaluation/evaluate_dynamic_agent.py
    python3 src/evaluation/evaluate_dynamic_agent.py --runs 2
    python3 src/evaluation/evaluate_dynamic_agent.py --include-unsupported

No cloud services or live market data are used.
"""

import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import statistics
import sys
import time
import traceback

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / "src" / "agents"
sys.path.insert(0, str(AGENTS_DIR))

from dynamic_energy_agent import MODEL, run_dynamic_agent  # noqa: E402


# Each test has a known, explicit tool-selection expectation.
# The unsupported case is optional because the current agent intentionally
# returns 'no_tools_selected' as a non-successful result.
CASES = [
    {
        "id": "overview_90d",
        "mode": "development_90d",
        "question": "What was the average electricity demand in the historical dataset?",
        "expected_tools": ["get_energy_overview"],
    },
    {
        "id": "quality_90d",
        "mode": "development_90d",
        "question": "Which variables have missing observations in the dataset?",
        "expected_tools": ["get_data_quality"],
    },
    {
        "id": "forecast_90d",
        "mode": "development_90d",
        "question": "Generate a one-hour-ahead historical electricity demand forecast.",
        "expected_tools": ["forecast_next_hour"],
    },
    {
        "id": "overview_full",
        "mode": "full_history",
        "question": "What was the average electricity demand across the full historical dataset?",
        "expected_tools": ["get_energy_overview"],
    },
    {
        "id": "quality_forecast_full",
        "mode": "full_history",
        "question": "Identify missing data and provide the historical one-hour demand forecast.",
        "expected_tools": ["get_data_quality", "forecast_next_hour"],
    },
    {
        "id": "overview_quality_90d",
        "mode": "development_90d",
        "question": "Summarize average electricity demand and identify missing observations.",
        "expected_tools": ["get_energy_overview", "get_data_quality"],
    },
    {
        "id": "all_three_90d",
        "mode": "development_90d",
        "question": (
            "Analyze average electricity demand, identify missing data, and "
            "generate a one-hour-ahead demand forecast. Explain the results "
            "with units, historical dates, and limitations."
        ),
        "expected_tools": [
            "get_energy_overview", "get_data_quality", "forecast_next_hour"
        ],
    },
    {
        "id": "all_three_full",
        "mode": "full_history",
        "question": (
            "For the full historical dataset, report average electricity demand, "
            "missing observations, and the one-hour-ahead historical forecast."
        ),
        "expected_tools": [
            "get_energy_overview", "get_data_quality", "forecast_next_hour"
        ],
    },
]

UNSUPPORTED_CASE = {
    "id": "unsupported_weather",
    "mode": "development_90d",
    "question": "What will the live weather in Amsterdam be tomorrow?",
    "expected_tools": [],
    "expected_status": "no_tools_selected",
}


def evaluate_case(case, repetition, quiet=False):
    """Execute one case, capturing both result and diagnostic console output."""
    output = io.StringIO()
    started = time.perf_counter()
    result = None
    exception = None
    try:
        with contextlib.redirect_stdout(output) if quiet else contextlib.nullcontext():
            result = run_dynamic_agent(case["question"], mode=case["mode"])
    except Exception as exc:
        exception = f"{type(exc).__name__}: {exc}"
        output.write(traceback.format_exc())
    elapsed = round(time.perf_counter() - started, 3)

    result = result if isinstance(result, dict) else {}
    actual = result.get("selected_tools", [])
    actual = actual if isinstance(actual, list) else []
    expected = case["expected_tools"]
    actual_set, expected_set = set(actual), set(expected)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    status = result.get("status", "exception")
    validation = result.get("validation") or {}
    validation_pass = validation.get("status") == "pass"
    attempts = result.get("attempts", 0)
    expected_status = case.get("expected_status", "completed")
    selection_exact = actual_set == expected_set and len(actual) == len(actual_set)
    status_match = status == expected_status
    # A zero-tool unsupported question is an intentional safe refusal, not
    # an ordinary validated analytical response.
    if expected_status == "no_tools_selected":
        outcome_pass = selection_exact and status_match
    else:
        outcome_pass = selection_exact and status_match and validation_pass

    return {
        "case_id": case["id"],
        "repetition": repetition,
        "dataset_mode": case["mode"],
        "question": case["question"],
        "expected_tools": expected,
        "actual_tools": actual,
        "missing_tools": missing,
        "unnecessary_tools": extra,
        "tool_selection_exact": selection_exact,
        "required_tool_recall": (
            len(expected_set & actual_set) / len(expected_set)
            if expected_set else (1.0 if not actual_set else 0.0)
        ),
        "status": status,
        "expected_status": expected_status,
        "status_match": status_match,
        "validation_pass": validation_pass,
        "validation_errors": validation.get("errors", []),
        "attempts": attempts,
        "first_attempt_pass": validation_pass and attempts == 1,
        "duration_seconds": elapsed,
        "dataset_mode_consistent": (
            result.get("dataset_mode") == case["mode"]
            and all(
                isinstance(v, dict) and v.get("dataset_mode") == case["mode"]
                for v in (result.get("tool_results") or {}).values()
            )
        ),
        "outcome_pass": outcome_pass,
        "answer": result.get("response", ""),
        "error": exception or result.get("error"),
        "console_log": output.getvalue() if quiet else "",
    }


def summarize(rows):
    total = len(rows)
    analytical = [r for r in rows if r["expected_tools"]]
    n = len(analytical)
    rate = lambda count, denom: round(100 * count / denom, 2) if denom else None
    return {
        "total_cases": total,
        "analytical_cases": n,
        "overall_scenario_pass_rate_pct": rate(sum(r["outcome_pass"] for r in rows), total),
        "exact_tool_selection_rate_pct": rate(sum(r["tool_selection_exact"] for r in rows), total),
        "mean_required_tool_recall_pct": round(100 * statistics.mean(r["required_tool_recall"] for r in rows), 2) if rows else None,
        "cases_with_unnecessary_tools": sum(bool(r["unnecessary_tools"]) for r in rows),
        "total_unnecessary_tool_calls": sum(len(r["unnecessary_tools"]) for r in rows),
        "validated_completion_rate_pct": rate(sum(r["validation_pass"] and r["status"] == "completed" for r in analytical), n),
        "first_attempt_pass_rate_pct": rate(sum(r["first_attempt_pass"] for r in analytical), n),
        "cases_requiring_retry": sum(r["attempts"] > 1 for r in analytical),
        "dataset_consistency_rate_pct": rate(sum(r["dataset_mode_consistent"] for r in rows), total),
        "average_duration_seconds": round(statistics.mean(r["duration_seconds"] for r in rows), 3) if rows else None,
        "median_duration_seconds": round(statistics.median(r["duration_seconds"] for r in rows), 3) if rows else None,
    }


def make_markdown(report):
    s = report["summary"]
    lines = [
        "# INNEVA.E — Dynamic Agent Evaluation (Checkpoint 18.4)", "",
        f"- Generated (UTC): {report['generated_at_utc']}",
        f"- Model: `{report['model']}`",
        f"- Runs per case: {report['runs_per_case']}",
        f"- Total cases: {s['total_cases']}", "",
        "## Summary", "",
    ]
    for key, value in s.items():
        lines.append(f"- **{key.replace('_', ' ').capitalize()}**: {value}")
    lines += [
        "", "## Case results", "",
        "| Case | Run | Mode | Expected tools | Actual tools | Status | Validation | Time (s) | Scenario pass |",
        "|---|---:|---|---|---|---|---|---:|---|",
    ]
    for r in report["results"]:
        lines.append(
            f"| {r['case_id']} | {r['repetition']} | {r['dataset_mode']} | "
            f"{', '.join(r['expected_tools']) or '(none)'} | "
            f"{', '.join(r['actual_tools']) or '(none)'} | {r['status']} | "
            f"{'pass' if r['validation_pass'] else 'not passed / N/A'} | "
            f"{r['duration_seconds']:.3f} | {'PASS' if r['outcome_pass'] else 'FAIL'} |"
        )
    lines += ["", "## Failures and limitations", ""]
    failures = [r for r in report["results"] if not r["outcome_pass"]]
    if failures:
        for r in failures:
            lines.append(f"- **{r['case_id']} (run {r['repetition']})**: status={r['status']}; "
                         f"missing={r['missing_tools']}; extra={r['unnecessary_tools']}; "
                         f"errors={r['validation_errors']}; exception={r['error']}")
    else:
        lines.append("- No failures in this sample.")
    lines += [
        "- These tests use historical snapshots, not live market data.",
        "- Exact tool selection is scored against manually specified expected sets.",
        "- A validator pass checks selected rules, not full factual correctness or answer completeness.",
        "- The unsupported test expects safe refusal (`no_tools_selected`), not a validated answer.",
        "- Small samples do not establish production reliability.", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Evaluate INNEVA.E dynamic agent locally")
    parser.add_argument("--runs", type=int, default=1, help="Repetitions per scenario (default: 1)")
    parser.add_argument("--include-unsupported", action="store_true", help="Also test refusal of unsupported live-weather question")
    parser.add_argument("--quiet", action="store_true", help="Capture verbose agent output instead of printing it")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    cases = CASES + ([UNSUPPORTED_CASE] if args.include_unsupported else [])
    results = []
    print(f"INNEVA.E DYNAMIC AGENT EVALUATION | model={MODEL} | scenarios={len(cases)} | repetitions={args.runs}")
    for case in cases:
        for repetition in range(1, args.runs + 1):
            print(f"\n[{len(results)+1}/{len(cases)*args.runs}] {case['id']} | {case['mode']}", flush=True)
            row = evaluate_case(case, repetition, quiet=args.quiet)
            results.append(row)
            print(f"RESULT: {'PASS' if row['outcome_pass'] else 'FAIL'} | "
                  f"tools={row['actual_tools']} | status={row['status']} | "
                  f"validation={'pass' if row['validation_pass'] else 'N/A or fail'} | "
                  f"{row['duration_seconds']}s", flush=True)
    report = {
        "checkpoint": "18.4", "model": MODEL,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runs_per_case": args.runs,
        "unsupported_case_included": args.include_unsupported,
        "summary": summarize(results), "results": results,
    }
    folder = PROJECT_ROOT / "reports" / "evaluation"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    basename = f"dynamic_agent_evaluation_{stamp}"
    json_path = folder / f"{basename}.json"
    md_path = folder / f"{basename}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(make_markdown(report), encoding="utf-8")
    print("\n" + "=" * 60)
    print(json.dumps(report["summary"], indent=2))
    print(f"\nJSON: {json_path}\nMarkdown: {md_path}")
    if not all(r["outcome_pass"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
