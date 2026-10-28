
"""
INNEVA.E — Multi-Origin Forecast Performance Analysis
Module 17.7C.2

Evaluate recursive ML against weekly seasonal naive
across eight non-overlapping seven-day forecast windows.

- Uses the existing unified forecast engine
- Uses actual demand only for evaluation
- Compares identical target hours
- Reports errors by origin and lead-time bucket
- Calculates per-origin model wins
- Exports CSV reports
- Does not modify the forecast registry, models, or source data

Historical evaluation only. These periods have previously
been inspected during model development.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from unified_forecast_engine import forecast
from evaluate_forecast_registry import load_actual_demand


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/multi_origin_monitoring"
)

ORIGINS = pd.date_range(
    start="2026-08-04T00:00:00Z",
    periods=8,
    freq="7D",
)

HORIZON = "7d"

METHODS = [
    "recursive_ml",
    "weekly_naive",
]


def lead_bucket(step):
    if step <= 24:
        return "01-24h"
    if step <= 72:
        return "25-72h"
    return "73-168h"


def metrics(data):
    if data.empty:
        raise ValueError("Cannot calculate metrics on empty data.")

    error = (
        data["predicted_demand_mw"].to_numpy(dtype=float)
        - data["actual_demand_mw"].to_numpy(dtype=float)
    )

    actual = data[
        "actual_demand_mw"
    ].to_numpy(dtype=float)

    if not np.isfinite(error).all():
        raise ValueError("Non-finite forecast errors found.")

    if not np.isfinite(actual).all() or (actual <= 0).any():
        raise ValueError("Missing or invalid actual demand.")

    return {
        "hours": len(data),
        "mae_mw": float(np.mean(np.abs(error))),
        "rmse_mw": float(
            np.sqrt(np.mean(np.square(error)))
        ),
        "mape_pct": float(
            100 * np.mean(np.abs(error / actual))
        ),
        "bias_mw": float(np.mean(error)),
    }


def group_metrics(data, columns):
    rows = []

    for key, group in data.groupby(
        columns,
        sort=True,
        dropna=False,
    ):
        if not isinstance(key, tuple):
            key = (key,)

        row = dict(zip(columns, key))
        row.update(metrics(group))
        rows.append(row)

    return pd.DataFrame(rows)


def main():
    print(
        "\nINNEVA.E — Multi-Origin Performance Analysis"
    )
    print("--------------------------------------------")

    actuals = load_actual_demand()

    all_predictions = []

    print("\nGENERATING FORECASTS")

    for origin in ORIGINS:
        issue_time = origin.isoformat()

        print(f"\nIssue time: {issue_time}")

        for method in METHODS:
            result = forecast(
                issue_time=issue_time,
                horizon=HORIZON,
                method=method,
            ).copy()

            if len(result) != 168:
                raise AssertionError(
                    f"Unexpected forecast length: {method}"
                )

            result["evaluation_origin_utc"] = origin
            result["evaluation_method"] = method

            all_predictions.append(result)

            print(
                f"  {method}: "
                f"{len(result)} predictions generated"
            )

    predictions = pd.concat(
        all_predictions,
        ignore_index=True,
    )

    predictions["forecast_time_utc"] = pd.to_datetime(
        predictions["forecast_time_utc"],
        utc=True,
    )

    predictions["evaluation_origin_utc"] = pd.to_datetime(
        predictions["evaluation_origin_utc"],
        utc=True,
    )

    predictions["step"] = predictions["step"].astype(int)

    predictions["lead_bucket"] = (
        predictions["step"].apply(lead_bucket)
    )

    # Confirm that the forecast target windows do not overlap.
    unique_windows = predictions[
        predictions["evaluation_method"] == METHODS[0]
    ]

    if unique_windows["forecast_time_utc"].duplicated().any():
        raise AssertionError(
            "Evaluation target windows overlap."
        )

    # Historical actuals are joined only after prediction.
    evaluated = predictions.merge(
        actuals,
        on="forecast_time_utc",
        how="left",
        validate="many_to_one",
    )

    if evaluated["actual_demand_mw"].isna().any():
        raise ValueError(
            "Some forecast target hours have no actual demand."
        )

    if (
        ~np.isfinite(
            evaluated["actual_demand_mw"].to_numpy(dtype=float)
        )
    ).any():
        raise ValueError(
            "Non-finite actual demand encountered."
        )

    if (evaluated["actual_demand_mw"] <= 0).any():
        raise ValueError(
            "Actual demand must be positive."
        )

    evaluated["error_mw"] = (
        evaluated["predicted_demand_mw"]
        - evaluated["actual_demand_mw"]
    )

    evaluated["absolute_error_mw"] = (
        evaluated["error_mw"].abs()
    )

    # Check both methods were evaluated against identical hours.
    targets_by_method = {
        method: set(
            evaluated.loc[
                evaluated["evaluation_method"] == method,
                [
                    "evaluation_origin_utc",
                    "forecast_time_utc",
                ],
            ].itertuples(index=False, name=None)
        )
        for method in METHODS
    }

    if (
        targets_by_method[METHODS[0]]
        != targets_by_method[METHODS[1]]
    ):
        raise AssertionError(
            "Model and benchmark target hours differ."
        )

    origin_metrics = group_metrics(
        evaluated,
        [
            "evaluation_origin_utc",
            "evaluation_method",
        ],
    )

    lead_metrics = group_metrics(
        evaluated,
        [
            "evaluation_method",
            "lead_bucket",
        ],
    )

    overall_metrics = group_metrics(
        evaluated,
        ["evaluation_method"],
    )

    origin_comparison = origin_metrics.pivot(
        index="evaluation_origin_utc",
        columns="evaluation_method",
        values="mae_mw",
    ).reset_index()

    origin_comparison["winner"] = np.where(
        origin_comparison["recursive_ml"]
        < origin_comparison["weekly_naive"],
        "recursive_ml",
        np.where(
            origin_comparison["recursive_ml"]
            > origin_comparison["weekly_naive"],
            "weekly_naive",
            "tie",
        ),
    )

    origin_comparison["ml_improvement_pct"] = (
        100
        * (
            origin_comparison["weekly_naive"]
            - origin_comparison["recursive_ml"]
        )
        / origin_comparison["weekly_naive"]
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    evaluated.to_csv(
        OUTPUT_DIR / "hourly_predictions.csv",
        index=False,
    )

    origin_metrics.to_csv(
        OUTPUT_DIR / "origin_performance.csv",
        index=False,
    )

    lead_metrics.to_csv(
        OUTPUT_DIR / "lead_time_performance.csv",
        index=False,
    )

    overall_metrics.to_csv(
        OUTPUT_DIR / "overall_performance.csv",
        index=False,
    )

    origin_comparison.to_csv(
        OUTPUT_DIR / "origin_comparison.csv",
        index=False,
    )

    print("\nEVALUATION COVERAGE")

    print(f"Forecast origins: {len(ORIGINS)}")
    print(f"Methods evaluated: {len(METHODS)}")
    print(f"Predictions per method: {8 * 168:,}")
    print(f"Total evaluated rows: {len(evaluated):,}")

    print("\nOVERALL PERFORMANCE")

    print(
        overall_metrics.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    print("\nLEAD-TIME PERFORMANCE")

    print(
        lead_metrics.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    print("\nPER-ORIGIN MAE COMPARISON")

    print(
        origin_comparison.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    wins = origin_comparison[
        "winner"
    ].value_counts()

    print("\nORIGIN WINS")

    for method in [
        "recursive_ml",
        "weekly_naive",
        "tie",
    ]:
        print(
            f"{method}: {int(wins.get(method, 0))}"
        )

    print("\nREPORTS SAVED TO")
    print(OUTPUT_DIR)

    print(
        "\nMULTI-ORIGIN PERFORMANCE ANALYSIS COMPLETE"
    )


if __name__ == "__main__":
    main()
