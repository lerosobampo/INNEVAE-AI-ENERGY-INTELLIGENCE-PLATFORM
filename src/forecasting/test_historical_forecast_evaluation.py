
"""
INNEVA.E — Historical Forecast Evaluation Test
Module 17.7B.2

Generates and registers a retrospective seven-day forecast,
compares it against historical actual demand, and independently
verifies MAE, RMSE, MAPE and signed bias.

Does not modify historical data or trained models.
Adds exactly one forecast run to the forecast registry.
"""

import numpy as np
import pandas as pd

from unified_forecast_engine import forecast
from forecast_registry import (
    initialize_registry,
    register_forecast,
    get_forecast,
    get_registry_summary,
)
from evaluate_forecast_registry import (
    evaluate_registry,
    load_actual_demand,
)


ISSUE_TIME = "2026-09-01T00:00:00+00:00"
HORIZON = "7d"
METHOD = "recursive_ml"


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS — {message}")


def close_enough(actual, expected, label):
    check(
        np.isclose(
            actual,
            expected,
            rtol=1e-10,
            atol=1e-8,
        ),
        f"{label} matches independent calculation",
    )


def main():
    print(
        "\nINNEVA.E — Historical Forecast Evaluation Tests"
    )
    print("------------------------------------------------")

    initialize_registry()
    before = get_registry_summary()

    print("\nTEST 1 — HISTORICAL FORECAST")

    predictions = forecast(
        issue_time=ISSUE_TIME,
        horizon=HORIZON,
        method=METHOD,
    )

    check(
        len(predictions) == 168,
        "Historical forecast contains 168 hours",
    )

    check(
        predictions["selected_method"].iloc[0]
        == "recursive_ml",
        "Recursive ML selected",
    )

    print(
        "Average predicted demand: "
        f"{predictions['predicted_demand_mw'].mean():,.2f} MW"
    )

    print("\nTEST 2 — REGISTER FORECAST")

    forecast_id = register_forecast(predictions)
    stored = get_forecast(forecast_id)

    check(
        len(stored) == 168,
        "Historical forecast registered and retrieved",
    )

    print(f"Forecast ID: {forecast_id}")

    print("\nTEST 3 — MATCH HISTORICAL ACTUALS")

    actuals = load_actual_demand()

    matched = stored.merge(
        actuals,
        on="forecast_time_utc",
        how="left",
        validate="many_to_one",
    )

    check(
        matched["actual_demand_mw"].notna().all(),
        "Actual demand exists for every forecast hour",
    )

    check(
        np.isfinite(
            matched["actual_demand_mw"].to_numpy(dtype=float)
        ).all(),
        "All actual demand values are finite",
    )

    check(
        (matched["actual_demand_mw"] > 0).all(),
        "All actual demand values are positive",
    )

    print("\nTEST 4 — INDEPENDENT ERROR CALCULATION")

    predicted = matched[
        "predicted_demand_mw"
    ].to_numpy(dtype=float)

    observed = matched[
        "actual_demand_mw"
    ].to_numpy(dtype=float)

    errors = predicted - observed

    expected_mae = float(np.mean(np.abs(errors)))
    expected_rmse = float(
        np.sqrt(np.mean(np.square(errors)))
    )
    expected_mape = float(
        100 * np.mean(np.abs(errors / observed))
    )
    expected_bias = float(np.mean(errors))

    print(f"Independent MAE:  {expected_mae:,.2f} MW")
    print(f"Independent RMSE: {expected_rmse:,.2f} MW")
    print(f"Independent MAPE: {expected_mape:,.2f}%")
    print(f"Independent bias: {expected_bias:,.2f} MW")

    print("\nTEST 5 — EVALUATOR CONSISTENCY")

    evaluated, summary = evaluate_registry()

    selected = summary.loc[
        summary["forecast_id"] == forecast_id
    ]

    check(
        len(selected) == 1,
        "Evaluator includes the registered historical forecast",
    )

    row = selected.iloc[0]

    check(
        int(row["evaluated_count"]) == 168,
        "All 168 historical predictions were evaluated",
    )

    check(
        int(row["pending_count"]) == 0,
        "No actual observations are pending",
    )

    check(
        row["forecast_origin_type"] == "retrospective",
        "Historical forecast is labeled retrospective",
    )

    close_enough(
        float(row["mae_mw"]),
        expected_mae,
        "MAE",
    )

    close_enough(
        float(row["rmse_mw"]),
        expected_rmse,
        "RMSE",
    )

    close_enough(
        float(row["mape_pct"]),
        expected_mape,
        "MAPE",
    )

    close_enough(
        float(row["bias_mw"]),
        expected_bias,
        "Signed bias",
    )

    print("\nTEST 6 — REGISTRY INTEGRITY")

    after = get_registry_summary()

    check(
        after["forecast_runs"]
        == before["forecast_runs"] + 1,
        "Exactly one forecast run was added",
    )

    check(
        after["forecast_predictions"]
        == before["forecast_predictions"] + 168,
        "Exactly 168 predictions were added",
    )

    current_run = evaluated.loc[
        evaluated["forecast_id"] == forecast_id
    ]

    check(
        (
            current_run["evaluation_status"] == "evaluated"
        ).all(),
        "All historical target hours have evaluated status",
    )

    print("\nFINAL EVALUATION RESULT")
    print(f"Forecast ID: {forecast_id}")
    print(f"MAE:         {row['mae_mw']:,.2f} MW")
    print(f"RMSE:        {row['rmse_mw']:,.2f} MW")
    print(f"MAPE:        {row['mape_pct']:,.2f}%")
    print(f"Bias:        {row['bias_mw']:,.2f} MW")

    print("\nREGISTRY SUMMARY")
    print(
        f"Forecast runs: {after['forecast_runs']:,}"
    )
    print(
        "Hourly predictions: "
        f"{after['forecast_predictions']:,}"
    )

    print(
        "\nALL HISTORICAL FORECAST EVALUATION TESTS PASSED"
    )


if __name__ == "__main__":
    main()
