
"""
INNEVA.E — Forecast Performance Monitoring
Module 17.7C.1

Analyzes registered forecast evaluation results.

Features:
- Forecast coverage and pending actuals
- Error metrics by model and horizon
- Error metrics by forecast lead-time bucket
- Retrospective vs contemporaneous run separation
- Data sufficiency checks for deterioration monitoring
- CSV monitoring reports

Read-only with respect to source data and registry.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_forecast_registry import evaluate_registry


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/forecast_monitoring"
)


def lead_bucket(step):
    if step <= 24:
        return "01-24h"
    if step <= 72:
        return "25-72h"
    if step <= 168:
        return "73-168h"
    return "169-720h"


def calculate_metrics(data):
    total = len(data)

    valid = data.loc[
        data["evaluation_status"] == "evaluated"
    ]

    count = len(valid)

    result = {
        "prediction_count": total,
        "evaluated_count": count,
        "pending_count": total - count,
        "coverage_pct": (
            100.0 * count / total
            if total else np.nan
        ),
        "mae_mw": np.nan,
        "rmse_mw": np.nan,
        "mape_pct": np.nan,
        "bias_mw": np.nan,
    }

    if count == 0:
        return result

    predicted = valid[
        "predicted_demand_mw"
    ].to_numpy(dtype=float)

    actual = valid[
        "actual_demand_mw"
    ].to_numpy(dtype=float)

    errors = predicted - actual

    result["mae_mw"] = float(
        np.mean(np.abs(errors))
    )

    result["rmse_mw"] = float(
        np.sqrt(np.mean(errors ** 2))
    )

    result["bias_mw"] = float(
        np.mean(errors)
    )

    nonzero = actual != 0

    if nonzero.any():
        result["mape_pct"] = float(
            100 * np.mean(
                np.abs(errors[nonzero] / actual[nonzero])
            )
        )

    return result


def group_metrics(data, columns):
    rows = []

    for key, group in data.groupby(
        columns,
        dropna=False,
        sort=True,
    ):
        if not isinstance(key, tuple):
            key = (key,)

        row = dict(zip(columns, key))

        row["forecast_runs"] = (
            group["forecast_id"].nunique()
        )

        row.update(calculate_metrics(group))
        rows.append(row)

    return pd.DataFrame(rows)


def monitor():
    evaluated, run_summary = evaluate_registry()

    if evaluated is None:
        print("No registered forecasts to monitor.")
        return

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    evaluated = evaluated.copy()

    evaluated["lead_bucket"] = (
        evaluated["step"].apply(lead_bucket)
    )

    model_metrics = group_metrics(
        evaluated,
        [
            "forecast_origin_type",
            "horizon",
            "selected_method",
            "model_version",
        ],
    )

    lead_metrics = group_metrics(
        evaluated,
        [
            "forecast_origin_type",
            "horizon",
            "selected_method",
            "lead_bucket",
        ],
    )

    run_metrics = group_metrics(
        evaluated,
        [
            "forecast_id",
            "forecast_origin_type",
            "horizon",
            "selected_method",
        ],
    )

    # Distinct runs are required to examine performance
    # over time. One historical run cannot establish drift.
    sufficient_runs = (
        run_metrics.loc[
            run_metrics["evaluated_count"] > 0
        ]
        .groupby(
            [
                "forecast_origin_type",
                "horizon",
                "selected_method",
            ]
        )["forecast_id"]
        .nunique()
        .reset_index(name="evaluated_forecast_runs")
    )

    sufficient_runs["monitoring_readiness"] = np.where(
        sufficient_runs["evaluated_forecast_runs"] >= 5,
        "candidate_for_trend_review",
        "insufficient_independent_runs",
    )

    # Five runs is only a preliminary reporting threshold.
    # Overlapping forecast windows are not independent,
    # and this threshold does not establish statistical drift.

    model_metrics.to_csv(
        OUTPUT_DIR / "model_performance.csv",
        index=False,
    )

    lead_metrics.to_csv(
        OUTPUT_DIR / "lead_time_performance.csv",
        index=False,
    )

    run_metrics.to_csv(
        OUTPUT_DIR / "forecast_run_performance.csv",
        index=False,
    )

    sufficient_runs.to_csv(
        OUTPUT_DIR / "monitoring_readiness.csv",
        index=False,
    )

    print("\nINNEVA.E — Forecast Performance Monitoring")
    print("------------------------------------------")

    print("\nREGISTRY COVERAGE")

    print(
        f"Forecast runs: {len(run_summary):,}"
    )

    print(
        f"Total predictions: {len(evaluated):,}"
    )

    print(
        "Evaluated predictions: "
        f"{(evaluated['evaluation_status'] == 'evaluated').sum():,}"
    )

    print(
        "Pending actuals: "
        f"{(evaluated['evaluation_status'] == 'pending_actual').sum():,}"
    )

    print("\nMODEL PERFORMANCE")

    print(
        model_metrics[
            [
                "forecast_origin_type",
                "horizon",
                "selected_method",
                "forecast_runs",
                "evaluated_count",
                "pending_count",
                "mae_mw",
                "mape_pct",
                "bias_mw",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    print("\nLEAD-TIME PERFORMANCE")

    print(
        lead_metrics[
            [
                "horizon",
                "selected_method",
                "lead_bucket",
                "evaluated_count",
                "mae_mw",
                "rmse_mw",
                "mape_pct",
                "bias_mw",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    print("\nMONITORING READINESS")

    if sufficient_runs.empty:
        print("No evaluated forecast runs.")
    else:
        print(
            sufficient_runs.to_string(
                index=False
            )
        )

    print("\nREPORTS SAVED TO")
    print(OUTPUT_DIR)

    print("\nPERFORMANCE MONITORING COMPLETE")


if __name__ == "__main__":
    monitor()
