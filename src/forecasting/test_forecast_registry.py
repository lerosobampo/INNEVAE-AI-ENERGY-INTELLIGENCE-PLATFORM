
"""
INNEVA.E — Forecast Registry Tests
Module 17.7A.2

Tests:
1. Forecast generation
2. SQLite registration
3. Forecast retrieval
4. Prediction integrity
5. Unique forecast IDs
6. Invalid forecast rejection
7. Registry summary consistency

This test intentionally writes forecast records
to the dedicated forecast registry database.

It does not modify historical datasets,
trained models, or the analytical database.
"""

import sqlite3

import numpy as np
import pandas as pd

from unified_forecast_engine import forecast

from forecast_registry import (
    DATABASE_PATH,
    initialize_registry,
    register_forecast,
    get_forecast,
    list_forecast_runs,
    get_registry_summary,
)


ISSUE_TIME = "2026-10-01T00:00:00+00:00"
HORIZON = "7d"
METHOD = "recursive_ml"


def check(condition, message):
    if not condition:
        raise AssertionError(message)

    print(f"PASS — {message}")


def expect_error(function, message):
    try:
        function()
    except (ValueError, TypeError, KeyError):
        print(f"PASS — {message}")
        return

    raise AssertionError(
        f"Expected validation error: {message}"
    )


def main():
    print(
        "\nINNEVA.E — Forecast Registry Tests"
    )
    print("----------------------------------")

    initialize_registry()

    initial_summary = get_registry_summary()

    print("\nINITIAL REGISTRY STATE")
    print(
        "Forecast runs: "
        f"{initial_summary['forecast_runs']:,}"
    )
    print(
        "Hourly predictions: "
        f"{initial_summary['forecast_predictions']:,}"
    )

    # ========================================================
    # TEST 1 — GENERATE FORECAST
    # ========================================================

    print("\nTEST 1 — GENERATE FORECAST")

    original = forecast(
        issue_time=ISSUE_TIME,
        horizon=HORIZON,
        method=METHOD,
    )

    check(
        len(original) == 168,
        "Seven-day forecast contains 168 hours",
    )

    check(
        original["selected_method"].iloc[0]
        == "recursive_ml",
        "Recursive ML was selected",
    )

    print(
        "Average predicted demand: "
        f"{original['predicted_demand_mw'].mean():,.2f} MW"
    )

    # ========================================================
    # TEST 2 — REGISTER FORECAST
    # ========================================================

    print("\nTEST 2 — REGISTER FORECAST")

    forecast_id = register_forecast(original)

    check(
        isinstance(forecast_id, str)
        and len(forecast_id) > 0,
        "Forecast registration returned an ID",
    )

    print(f"Forecast ID: {forecast_id}")

    # ========================================================
    # TEST 3 — RETRIEVE FORECAST
    # ========================================================

    print("\nTEST 3 — RETRIEVE FORECAST")

    retrieved = get_forecast(forecast_id)

    check(
        len(retrieved) == 168,
        "Retrieved forecast contains 168 rows",
    )

    check(
        retrieved["forecast_id"].nunique() == 1,
        "Retrieved rows belong to one forecast",
    )

    check(
        retrieved["forecast_id"].iloc[0]
        == forecast_id,
        "Retrieved forecast ID matches",
    )

    # ========================================================
    # TEST 4 — PREDICTION INTEGRITY
    # ========================================================

    print("\nTEST 4 — PREDICTION INTEGRITY")

    original_values = original[
        "predicted_demand_mw"
    ].to_numpy(dtype=float)

    retrieved_values = retrieved[
        "predicted_demand_mw"
    ].to_numpy(dtype=float)

    check(
        np.array_equal(
            original_values,
            retrieved_values,
        ),
        "All 168 predictions match exactly",
    )

    check(
        np.array_equal(
            original["step"].to_numpy(),
            retrieved["step"].to_numpy(),
        ),
        "Forecast lead steps match",
    )

    original_times = pd.to_datetime(
        original["forecast_time_utc"],
        utc=True,
    )

    retrieved_times = pd.to_datetime(
        retrieved["forecast_time_utc"],
        utc=True,
    )

    check(
        original_times.reset_index(drop=True).equals(
            retrieved_times.reset_index(drop=True)
        ),
        "All target timestamps match",
    )

    check(
        retrieved["model_version"].iloc[0].startswith(
            "recursive_ml_sha256_"
        ),
        "Model artifact checksum is recorded",
    )

    # ========================================================
    # TEST 5 — UNIQUE REGISTRATIONS
    # ========================================================

    print("\nTEST 5 — UNIQUE REGISTRATIONS")

    second_id = register_forecast(original)

    check(
        second_id != forecast_id,
        "Identical forecasts receive unique IDs",
    )

    second = get_forecast(second_id)

    check(
        np.array_equal(
            second["predicted_demand_mw"].to_numpy(),
            original_values,
        ),
        "Second registration preserves predictions",
    )

    # ========================================================
    # TEST 6 — INVALID FORECAST REJECTION
    # ========================================================

    print("\nTEST 6 — INVALID FORECAST REJECTION")

    before_invalid = get_registry_summary()

    invalid = original.copy()

    invalid.loc[
        invalid.index[0],
        "predicted_demand_mw",
    ] = -100.0

    expect_error(
        lambda: register_forecast(invalid),
        "Negative demand is rejected",
    )

    incomplete = original.iloc[:-1].copy()

    expect_error(
        lambda: register_forecast(incomplete),
        "Incomplete forecast is rejected",
    )

    wrong_steps = original.copy()

    wrong_steps.loc[
        wrong_steps.index[0],
        "step",
    ] = 999

    expect_error(
        lambda: register_forecast(wrong_steps),
        "Invalid lead steps are rejected",
    )

    after_invalid = get_registry_summary()

    check(
        before_invalid == after_invalid,
        "Invalid forecasts do not change registry counts",
    )

    # ========================================================
    # TEST 7 — DATABASE INTEGRITY
    # ========================================================

    print("\nTEST 7 — DATABASE INTEGRITY")

    with sqlite3.connect(DATABASE_PATH) as connection:
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    check(
        len(foreign_keys) == 0,
        "No foreign-key integrity violations",
    )

    final_summary = get_registry_summary()

    check(
        final_summary["forecast_runs"]
        == initial_summary["forecast_runs"] + 2,
        "Exactly two forecast runs were added",
    )

    check(
        final_summary["forecast_predictions"]
        == initial_summary["forecast_predictions"] + 336,
        "Exactly 336 hourly predictions were added",
    )

    recent_runs = list_forecast_runs(limit=5)

    check(
        len(recent_runs) >= 2,
        "Recent forecast runs can be listed",
    )

    print("\nFINAL REGISTRY SUMMARY")

    print(
        "Forecast runs: "
        f"{final_summary['forecast_runs']:,}"
    )

    print(
        "Hourly predictions: "
        f"{final_summary['forecast_predictions']:,}"
    )

    print("\nREGISTERED FORECASTS")

    print(f"First ID:  {forecast_id}")
    print(f"Second ID: {second_id}")

    print("\nDATABASE LOCATION")
    print(DATABASE_PATH)

    print(
        "\nALL FORECAST REGISTRY TESTS PASSED"
    )


if __name__ == "__main__":
    main()
