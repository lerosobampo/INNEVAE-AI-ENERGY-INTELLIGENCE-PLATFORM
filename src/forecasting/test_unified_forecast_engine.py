
from pathlib import Path

import numpy as np
import pandas as pd

from unified_forecast_engine import (
    forecast,
    prepare_history,
    AUTO_METHODS,
    SUPPORTED_METHODS,
)
from one_hour_forecast import load_historical_data


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ISSUE_TIME = pd.Timestamp(
    "2026-10-01T00:00:00+00:00"
)

HORIZONS = {
    "1h": 1,
    "24h": 24,
    "7d": 168,
    "30d": 720,
}


def check(condition, message):
    if not condition:
        raise AssertionError(message)

    print(f"PASS — {message}")


def expect_error(function, message):
    try:
        function()
    except (ValueError, KeyError):
        print(f"PASS — {message}")
        return

    raise AssertionError(
        f"Expected an error: {message}"
    )


def longest_constant_run(values, tolerance=1e-8):
    values = np.asarray(values, dtype=float)

    if len(values) == 0:
        return 0

    longest = 1
    current = 1

    for i in range(1, len(values)):
        if np.isclose(
            values[i],
            values[i - 1],
            rtol=0,
            atol=tolerance,
        ):
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return longest


def test_supported_horizons(history):
    print("\nTEST 1 — SUPPORTED HORIZONS")

    for horizon, expected_hours in HORIZONS.items():
        result = forecast(
            issue_time=ISSUE_TIME,
            horizon=horizon,
            method="auto",
            historical_data=history,
        )

        check(
            len(result) == expected_hours,
            f"{horizon} returns {expected_hours} rows",
        )

        check(
            result["selected_method"].iloc[0]
            == AUTO_METHODS[horizon],
            f"{horizon} selects the expected method",
        )

        check(
            np.isfinite(
                result["predicted_demand_mw"]
            ).all(),
            f"{horizon} predictions are finite",
        )

        check(
            (
                result["predicted_demand_mw"] > 0
            ).all(),
            f"{horizon} predictions are positive",
        )

        expected_times = pd.date_range(
            start=ISSUE_TIME,
            periods=expected_hours,
            freq="h",
        )

        check(
            pd.DatetimeIndex(
                result["forecast_time_utc"]
            ).equals(expected_times),
            f"{horizon} timestamps are consecutive",
        )


def test_recursive_consistency(history):
    print("\nTEST 2 — RECURSIVE CONSISTENCY")

    one_hour = forecast(
        issue_time=ISSUE_TIME,
        horizon="1h",
        method="recursive_ml",
        historical_data=history,
    )

    seven_days = forecast(
        issue_time=ISSUE_TIME,
        horizon="7d",
        method="recursive_ml",
        historical_data=history,
    )

    check(
        np.isclose(
            one_hour["predicted_demand_mw"].iloc[0],
            seven_days["predicted_demand_mw"].iloc[0],
            rtol=0,
            atol=1e-8,
        ),
        "One-hour forecast matches first recursive step",
    )


def test_seasonal_naive(history):
    print("\nTEST 3 — SEASONAL BASELINES")

    prepared = prepare_history(
        history,
        ISSUE_TIME,
    )

    demand = prepared.set_index(
        "hour_start_utc"
    )["actual_load_mw"]

    daily = forecast(
        issue_time=ISSUE_TIME,
        horizon="24h",
        method="daily_naive",
        historical_data=history,
    )

    expected_daily = demand.loc[
        pd.date_range(
            end=ISSUE_TIME - pd.Timedelta(hours=1),
            periods=24,
            freq="h",
        )
    ].to_numpy()

    check(
        np.allclose(
            daily["predicted_demand_mw"],
            expected_daily,
        ),
        "Daily naive repeats the last 24 observed hours",
    )

    weekly = forecast(
        issue_time=ISSUE_TIME,
        horizon="7d",
        method="weekly_naive",
        historical_data=history,
    )

    expected_weekly = demand.loc[
        pd.date_range(
            end=ISSUE_TIME - pd.Timedelta(hours=1),
            periods=168,
            freq="h",
        )
    ].to_numpy()

    check(
        np.allclose(
            weekly["predicted_demand_mw"],
            expected_weekly,
        ),
        "Weekly naive repeats the last 168 observed hours",
    )


def test_direct_model(history):
    print("\nTEST 4 — DIRECT MODEL")

    direct = forecast(
        issue_time=ISSUE_TIME,
        horizon="30d",
        method="direct_ml",
        historical_data=history,
    )

    values = direct[
        "predicted_demand_mw"
    ].to_numpy()

    check(
        len(values) == 720,
        "Direct model returns 720 predictions",
    )

    check(
        np.isfinite(values).all(),
        "Direct model predictions are finite",
    )

    check(
        (values > 0).all(),
        "Direct model predictions are positive",
    )

    run_length = longest_constant_run(values)

    unique_values = len(
        np.unique(np.round(values, 6))
    )

    print("\nDIRECT MODEL DIAGNOSTICS")
    print(f"Unique predictions: {unique_values}")
    print(
        "Longest consecutive constant sequence: "
        f"{run_length} hours"
    )
    print(
        "Prediction standard deviation: "
        f"{values.std():,.2f} MW"
    )

    if run_length >= 12:
        print(
            "WARNING — Direct model has a flat "
            "prediction sequence of at least 12 hours."
        )

    if unique_values < 100:
        print(
            "WARNING — Direct model has fewer than "
            "100 unique predictions across 720 hours."
        )


def test_invalid_inputs(history):
    print("\nTEST 5 — INVALID INPUTS")

    expect_error(
        lambda: forecast(
            issue_time=ISSUE_TIME,
            horizon="48h",
            historical_data=history,
        ),
        "Unsupported horizon is rejected",
    )

    expect_error(
        lambda: forecast(
            issue_time=ISSUE_TIME,
            horizon="24h",
            method="unknown_model",
            historical_data=history,
        ),
        "Unsupported forecasting method is rejected",
    )

    expect_error(
        lambda: forecast(
            issue_time="2026-10-01T00:30:00+00:00",
            horizon="24h",
            historical_data=history,
        ),
        "Non-hour-aligned issue time is rejected",
    )

    expect_error(
        lambda: forecast(
            issue_time="2026-10-01 00:00:00",
            horizon="24h",
            historical_data=history,
        ),
        "Timezone-naive issue time is rejected",
    )


def test_missing_history(history):
    print("\nTEST 6 — HISTORICAL DATA VALIDATION")

    missing_latest = history[
        history["hour_start_utc"]
        != ISSUE_TIME - pd.Timedelta(hours=1)
    ].copy()

    expect_error(
        lambda: forecast(
            issue_time=ISSUE_TIME,
            horizon="24h",
            method="daily_naive",
            historical_data=missing_latest,
        ),
        "Missing latest observation is rejected",
    )

    duplicated = pd.concat(
        [
            history,
            history.tail(1),
        ],
        ignore_index=True,
    )

    expect_error(
        lambda: forecast(
            issue_time=ISSUE_TIME,
            horizon="24h",
            method="daily_naive",
            historical_data=duplicated,
        ),
        "Duplicate historical timestamp is rejected",
    )

    invalid = history.copy()

    invalid.loc[
        invalid.index[-1],
        "actual_load_mw",
    ] = np.nan

    expect_error(
        lambda: forecast(
            issue_time=ISSUE_TIME,
            horizon="24h",
            method="daily_naive",
            historical_data=invalid,
        ),
        "Invalid recent demand is rejected",
    )


def test_future_data_leakage(history):
    print("\nTEST 7 — FUTURE-DATA LEAKAGE")

    baseline = forecast(
        issue_time=ISSUE_TIME,
        horizon="24h",
        method="daily_naive",
        historical_data=history,
    )

    contaminated = pd.concat(
        [
            history,
            pd.DataFrame({
                "hour_start_utc": [
                    ISSUE_TIME,
                    ISSUE_TIME + pd.Timedelta(hours=1),
                ],
                "actual_load_mw": [
                    999999.0,
                    999999.0,
                ],
            }),
        ],
        ignore_index=True,
    )

    result = forecast(
        issue_time=ISSUE_TIME,
        horizon="24h",
        method="daily_naive",
        historical_data=contaminated,
    )

    check(
        np.allclose(
            baseline["predicted_demand_mw"],
            result["predicted_demand_mw"],
        ),
        "Future actual observations do not change "
        "the forecast",
    )


def main():
    print(
        "\nINNEVA.E — Unified Forecast Engine Tests"
    )
    print("----------------------------------------")

    history = load_historical_data()

    test_supported_horizons(history)
    test_recursive_consistency(history)
    test_seasonal_naive(history)
    test_direct_model(history)
    test_invalid_inputs(history)
    test_missing_history(history)
    test_future_data_leakage(history)

    print("\nALL FORECAST ENGINE TESTS PASSED")


if __name__ == "__main__":
    main()
