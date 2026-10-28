
"""
INNEVA.E — Forecast Reliability Assessment
Module 17.7C.3

Evaluates the consistency and reliability of recursive ML
against the weekly seasonal naive benchmark.

Inputs:
    data/processed/multi_origin_monitoring/
        origin_comparison.csv
        origin_performance.csv
        overall_performance.csv
        lead_time_performance.csv

Outputs:
    data/processed/forecast_reliability/
        reliability_summary.csv
        weekly_reliability.csv
        lead_time_reliability.csv
        reliability_report.txt

This is a retrospective diagnostic assessment.
It does not establish out-of-sample reliability.

No models, source datasets, or databases are modified.
"""

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/multi_origin_monitoring"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/forecast_reliability"
)

ML_METHOD = "recursive_ml"
BASELINE_METHOD = "weekly_naive"

MIN_ORIGINS = 12
MIN_WIN_RATE = 60.0
MIN_MAE_IMPROVEMENT = 5.0
MAX_WEEKLY_REGRESSION = -20.0

# The current August-September 2026 evaluation window
# was inspected during earlier model development.
UNTOUCHED_EVALUATION = False


def load_reports():
    filenames = {
        "comparison": "origin_comparison.csv",
        "origin": "origin_performance.csv",
        "overall": "overall_performance.csv",
        "lead": "lead_time_performance.csv",
    }

    reports = {}

    for name, filename in filenames.items():
        path = INPUT_DIR / filename

        if not path.exists():
            raise FileNotFoundError(
                f"Required monitoring report missing: {path}"
            )

        reports[name] = pd.read_csv(path)

        if reports[name].empty:
            raise ValueError(
                f"Monitoring report is empty: {filename}"
            )

    return reports


def validate_reports(reports):
    comparison = reports["comparison"]
    origin = reports["origin"]
    overall = reports["overall"]
    lead = reports["lead"]

    required_comparison = {
        "evaluation_origin_utc",
        ML_METHOD,
        BASELINE_METHOD,
    }

    required_origin = {
        "evaluation_origin_utc",
        "evaluation_method",
        "hours",
        "mae_mw",
    }

    required_overall = {
        "evaluation_method",
        "hours",
        "mae_mw",
    }

    required_lead = {
        "evaluation_method",
        "lead_bucket",
        "hours",
        "mae_mw",
    }

    requirements = [
        ("comparison", comparison, required_comparison),
        ("origin", origin, required_origin),
        ("overall", overall, required_overall),
        ("lead", lead, required_lead),
    ]

    for name, df, required in requirements:
        missing = required - set(df.columns)

        if missing:
            raise ValueError(
                f"{name} report missing columns: "
                f"{sorted(missing)}"
            )

    comparison["evaluation_origin_utc"] = pd.to_datetime(
        comparison["evaluation_origin_utc"],
        utc=True,
        errors="raise",
    )

    origin["evaluation_origin_utc"] = pd.to_datetime(
        origin["evaluation_origin_utc"],
        utc=True,
        errors="raise",
    )

    if comparison["evaluation_origin_utc"].duplicated().any():
        raise ValueError(
            "Duplicate origins in comparison report."
        )

    if origin.duplicated(
        ["evaluation_origin_utc", "evaluation_method"]
    ).any():
        raise ValueError(
            "Duplicate origin-method records."
        )

    if overall["evaluation_method"].duplicated().any():
        raise ValueError(
            "Duplicate overall method records."
        )

    if lead.duplicated(
        ["evaluation_method", "lead_bucket"]
    ).any():
        raise ValueError(
            "Duplicate lead-time method records."
        )

    expected_methods = {ML_METHOD, BASELINE_METHOD}

    for name in ["origin", "overall", "lead"]:
        actual_methods = set(
            reports[name]["evaluation_method"]
        )

        if actual_methods != expected_methods:
            raise ValueError(
                f"Unexpected methods in {name}: "
                f"{actual_methods}"
            )

    for method in [ML_METHOD, BASELINE_METHOD]:
        comparison[method] = pd.to_numeric(
            comparison[method],
            errors="raise",
        )

        values = comparison[method].to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or (values <= 0).any()
        ):
            raise ValueError(
                f"Invalid comparison MAE for {method}."
            )

    for name in ["origin", "overall", "lead"]:
        df = reports[name]

        for column in ["hours", "mae_mw"]:
            df[column] = pd.to_numeric(
                df[column],
                errors="raise",
            )

        if (
            not np.isfinite(
                df[["hours", "mae_mw"]].to_numpy(dtype=float)
            ).all()
            or (df["hours"] <= 0).any()
            or (df["mae_mw"] < 0).any()
        ):
            raise ValueError(
                f"Invalid numeric values in {name} report."
            )

    # Ensure comparison MAEs match the per-origin report.
    pivot = origin.pivot(
        index="evaluation_origin_utc",
        columns="evaluation_method",
        values="mae_mw",
    )

    indexed = comparison.set_index(
        "evaluation_origin_utc"
    )

    if set(pivot.index) != set(indexed.index):
        raise ValueError(
            "Comparison and origin reports cover "
            "different forecast origins."
        )

    for method in [ML_METHOD, BASELINE_METHOD]:
        aligned = pivot[method].reindex(indexed.index)

        if not np.allclose(
            aligned.to_numpy(dtype=float),
            indexed[method].to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-6,
        ):
            raise ValueError(
                f"MAE disagreement between reports: {method}"
            )

    # Validate each origin contains a matched full horizon.
    hours_pivot = origin.pivot(
        index="evaluation_origin_utc",
        columns="evaluation_method",
        values="hours",
    )

    if not (
        (hours_pivot[ML_METHOD] == 168)
        & (hours_pivot[BASELINE_METHOD] == 168)
    ).all():
        raise ValueError(
            "Each origin must contain 168 evaluated "
            "hours for both methods."
        )

    origins = comparison[
        "evaluation_origin_utc"
    ].sort_values()

    if (
        origins.diff().dropna()
        < pd.Timedelta(days=7)
    ).any():
        raise ValueError(
            "Evaluation origins overlap within seven days."
        )

    for method in [ML_METHOD, BASELINE_METHOD]:
        expected_hours = 168 * len(comparison)

        overall_row = overall.loc[
            overall["evaluation_method"] == method
        ].iloc[0]

        if int(overall_row["hours"]) != expected_hours:
            raise ValueError(
                f"Overall hours mismatch for {method}."
            )

        expected_mae = float(
            origin.loc[
                origin["evaluation_method"] == method,
                "mae_mw",
            ].mean()
        )

        if not np.isclose(
            float(overall_row["mae_mw"]),
            expected_mae,
            rtol=1e-9,
            atol=1e-6,
        ):
            raise ValueError(
                f"Overall MAE mismatch for {method}."
            )

        lead_rows = lead.loc[
            lead["evaluation_method"] == method
        ]

        if int(lead_rows["hours"].sum()) != expected_hours:
            raise ValueError(
                f"Lead-time coverage mismatch for {method}."
            )

        weighted_lead_mae = np.average(
            lead_rows["mae_mw"],
            weights=lead_rows["hours"],
        )

        if not np.isclose(
            weighted_lead_mae,
            float(overall_row["mae_mw"]),
            rtol=1e-9,
            atol=1e-6,
        ):
            raise ValueError(
                f"Lead-time MAE mismatch for {method}."
            )


def build_weekly_reliability(comparison):
    weekly = comparison[
        [
            "evaluation_origin_utc",
            ML_METHOD,
            BASELINE_METHOD,
        ]
    ].copy()

    weekly = weekly.sort_values(
        "evaluation_origin_utc"
    ).reset_index(drop=True)

    weekly = weekly.rename(
        columns={
            ML_METHOD: "ml_mae_mw",
            BASELINE_METHOD: "baseline_mae_mw",
        }
    )

    weekly["ml_improvement_pct"] = (
        100.0
        * (
            weekly["baseline_mae_mw"]
            - weekly["ml_mae_mw"]
        )
        / weekly["baseline_mae_mw"]
    )

    weekly["winner"] = np.select(
        [
            weekly["ml_mae_mw"]
            < weekly["baseline_mae_mw"],
            weekly["ml_mae_mw"]
            > weekly["baseline_mae_mw"],
        ],
        [
            ML_METHOD,
            BASELINE_METHOD,
        ],
        default="tie",
    )

    weekly["absolute_mae_difference_mw"] = (
        weekly["baseline_mae_mw"]
        - weekly["ml_mae_mw"]
    )

    return weekly


def build_lead_reliability(lead):
    pivot = lead.pivot(
        index="lead_bucket",
        columns="evaluation_method",
        values="mae_mw",
    )

    result = pivot.reset_index()

    result = result.rename(
        columns={
            ML_METHOD: "ml_mae_mw",
            BASELINE_METHOD: "baseline_mae_mw",
        }
    )

    result["ml_improvement_pct"] = (
        100.0
        * (
            result["baseline_mae_mw"]
            - result["ml_mae_mw"]
        )
        / result["baseline_mae_mw"]
    )

    result["winner"] = np.where(
        result["ml_mae_mw"] < result["baseline_mae_mw"],
        ML_METHOD,
        np.where(
            result["ml_mae_mw"] > result["baseline_mae_mw"],
            BASELINE_METHOD,
            "tie",
        ),
    )

    return result.sort_values(
        "lead_bucket"
    ).reset_index(drop=True)


def assess_reliability(reports):
    weekly = build_weekly_reliability(
        reports["comparison"]
    )

    lead = build_lead_reliability(
        reports["lead"]
    )

    overall = reports["overall"].set_index(
        "evaluation_method"
    )

    ml_mae = float(
        overall.loc[ML_METHOD, "mae_mw"]
    )

    baseline_mae = float(
        overall.loc[BASELINE_METHOD, "mae_mw"]
    )

    overall_improvement = (
        100.0
        * (baseline_mae - ml_mae)
        / baseline_mae
    )

    total_origins = len(weekly)

    ml_wins = int(
        (weekly["winner"] == ML_METHOD).sum()
    )

    baseline_wins = int(
        (weekly["winner"] == BASELINE_METHOD).sum()
    )

    ties = int(
        (weekly["winner"] == "tie").sum()
    )

    win_rate = (
        100.0 * ml_wins / total_origins
    )

    worst_regression = float(
        weekly["ml_improvement_pct"].min()
    )

    best_improvement = float(
        weekly["ml_improvement_pct"].max()
    )

    ml_mae_std = float(
        weekly["ml_mae_mw"].std(ddof=1)
    ) if total_origins > 1 else np.nan

    baseline_mae_std = float(
        weekly["baseline_mae_mw"].std(ddof=1)
    ) if total_origins > 1 else np.nan

    checks = {
        "sufficient_origins": (
            total_origins >= MIN_ORIGINS
        ),
        "sufficient_win_rate": (
            win_rate >= MIN_WIN_RATE
        ),
        "sufficient_mae_improvement": (
            overall_improvement >= MIN_MAE_IMPROVEMENT
        ),
        "acceptable_worst_regression": (
            worst_regression >= MAX_WEEKLY_REGRESSION
        ),
        "untouched_evaluation": (
            UNTOUCHED_EVALUATION
        ),
    }

    passed_checks = sum(checks.values())

    all_passed = all(checks.values())

    if all_passed:
        recommendation = (
            "candidate_for_independent_validation"
        )
        reliability_status = (
            "provisional_criteria_met"
        )
    else:
        recommendation = (
            "retain_provisional_default_and_monitor"
            if overall_improvement > 0
            else "review_default_against_baseline"
        )
        reliability_status = (
            "limited_evidence"
        )

    summary = {
        "forecast_horizon": "7d",
        "ml_method": ML_METHOD,
        "baseline_method": BASELINE_METHOD,
        "forecast_origins": total_origins,
        "ml_wins": ml_wins,
        "baseline_wins": baseline_wins,
        "ties": ties,
        "ml_win_rate_pct": win_rate,
        "ml_mae_mw": ml_mae,
        "baseline_mae_mw": baseline_mae,
        "overall_ml_improvement_pct": overall_improvement,
        "worst_weekly_improvement_pct": worst_regression,
        "best_weekly_improvement_pct": best_improvement,
        "ml_weekly_mae_std_mw": ml_mae_std,
        "baseline_weekly_mae_std_mw": baseline_mae_std,
        "checks_passed": passed_checks,
        "checks_total": len(checks),
        "reliability_status": reliability_status,
        "recommendation": recommendation,
        "evaluation_type": (
            "retrospective_development_period"
        ),
        "untouched_evaluation": UNTOUCHED_EVALUATION,
    }

    for name, passed in checks.items():
        summary[f"check_{name}"] = bool(passed)

    return summary, weekly, lead


def write_text_report(summary, weekly, lead):
    lines = [
        "INNEVA.E — FORECAST RELIABILITY REPORT",
        "=" * 44,
        "",
        "EVALUATION CONTEXT",
        "------------------",
        "Horizon: 7 days",
        "ML method: recursive_ml",
        "Benchmark: weekly_naive",
        "Evaluation: retrospective development period",
        "Untouched holdout: No",
        "",
        "OVERALL PERFORMANCE",
        "-------------------",
        f"Origins: {summary['forecast_origins']}",
        f"ML MAE: {summary['ml_mae_mw']:,.2f} MW",
        (
            "Baseline MAE: "
            f"{summary['baseline_mae_mw']:,.2f} MW"
        ),
        (
            "Overall ML improvement: "
            f"{summary['overall_ml_improvement_pct']:.2f}%"
        ),
        "",
        "CONSISTENCY",
        "-----------",
        f"ML wins: {summary['ml_wins']}",
        f"Baseline wins: {summary['baseline_wins']}",
        f"Ties: {summary['ties']}",
        (
            "ML win rate: "
            f"{summary['ml_win_rate_pct']:.1f}%"
        ),
        "",
        "WEEKLY RISK",
        "-----------",
        (
            "Worst ML improvement: "
            f"{summary['worst_weekly_improvement_pct']:.2f}%"
        ),
        (
            "Best ML improvement: "
            f"{summary['best_weekly_improvement_pct']:.2f}%"
        ),
        (
            "ML weekly MAE standard deviation: "
            f"{summary['ml_weekly_mae_std_mw']:.2f} MW"
        ),
        (
            "Baseline weekly MAE standard deviation: "
            f"{summary['baseline_weekly_mae_std_mw']:.2f} MW"
        ),
        "",
        "RELIABILITY ASSESSMENT",
        "----------------------",
        (
            "Checks passed: "
            f"{summary['checks_passed']}/"
            f"{summary['checks_total']}"
        ),
        f"Status: {summary['reliability_status']}",
        f"Recommendation: {summary['recommendation']}",
        "",
        "WEEKLY RESULTS",
        "--------------",
        weekly.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        ),
        "",
        "LEAD-TIME RESULTS",
        "-----------------",
        lead.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        ),
        "",
        "INTERPRETATION",
        "--------------",
        (
            "This report is a retrospective diagnostic, "
            "not an unbiased estimate of future performance."
        ),
        (
            "The criteria are provisional engineering "
            "thresholds, not statistical guarantees."
        ),
        (
            "Do not automatically change model selection "
            "based on this report alone."
        ),
        "",
    ]

    report_path = (
        OUTPUT_DIR / "reliability_report.txt"
    )

    report_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return report_path


def main():
    print(
        "\nINNEVA.E — Forecast Reliability Assessment"
    )
    print("------------------------------------------")

    reports = load_reports()
    validate_reports(reports)

    summary, weekly, lead = assess_reliability(
        reports
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    pd.DataFrame([summary]).to_csv(
        OUTPUT_DIR / "reliability_summary.csv",
        index=False,
    )

    weekly.to_csv(
        OUTPUT_DIR / "weekly_reliability.csv",
        index=False,
    )

    lead.to_csv(
        OUTPUT_DIR / "lead_time_reliability.csv",
        index=False,
    )

    report_path = write_text_report(
        summary,
        weekly,
        lead,
    )

    print("\nOVERALL RESULTS")

    print(
        f"Forecast origins: "
        f"{summary['forecast_origins']}"
    )

    print(
        f"ML MAE: {summary['ml_mae_mw']:,.2f} MW"
    )

    print(
        "Baseline MAE: "
        f"{summary['baseline_mae_mw']:,.2f} MW"
    )

    print(
        "ML improvement: "
        f"{summary['overall_ml_improvement_pct']:.2f}%"
    )

    print("\nCONSISTENCY")

    print(
        f"ML wins: {summary['ml_wins']}"
    )

    print(
        f"Baseline wins: {summary['baseline_wins']}"
    )

    print(
        "ML win rate: "
        f"{summary['ml_win_rate_pct']:.1f}%"
    )

    print(
        "Worst weekly improvement: "
        f"{summary['worst_weekly_improvement_pct']:.2f}%"
    )

    print("\nRELIABILITY DECISION")

    print(
        f"Checks passed: "
        f"{summary['checks_passed']}/"
        f"{summary['checks_total']}"
    )

    print(
        f"Status: {summary['reliability_status']}"
    )

    print(
        f"Recommendation: {summary['recommendation']}"
    )

    print("\nREPORT SAVED TO")
    print(report_path)

    print(
        "\nFORECAST RELIABILITY ASSESSMENT COMPLETE"
    )


if __name__ == "__main__":
    main()
