
import numpy as np
import pandas as pd

from one_hour_forecast import (
    load_historical_data,
    forecast_one_hour,
)
from multi_hour_forecast import forecast_multiple_hours


ISSUE_TIME = pd.Timestamp(
    "2026-10-01T00:00:00+00:00"
)

HORIZON = "24h"


def check(condition, message):
    if not condition:
        raise AssertionError(message)

    print(f"PASS — {message}")


def main():
    print("\nINNEVA.E — Recursive Forecast Tests")

    historical = load_historical_data()

    # Test 1: Generate 24 hourly predictions
    forecast = forecast_multiple_hours(
        issue_time=ISSUE_TIME,
        horizon=HORIZON,
        historical_data=historical,
    )

    check(
        len(forecast) == 24,
        "24 hourly predictions generated",
    )

    # Test 2: Validate forecast timestamps
    expected_times = pd.date_range(
        start=ISSUE_TIME,
        periods=24,
        freq="h",
    )

    actual_times = pd.DatetimeIndex(
        pd.to_datetime(
            forecast["forecast_time_utc"],
            utc=True,
        )
    )

    check(
        actual_times.equals(expected_times),
        "Forecast timestamps are consecutive",
    )

    # Test 3: First prediction matches one-hour engine
    one_hour = forecast_one_hour(ISSUE_TIME)

    first_recursive = float(
        forecast["predicted_demand_mw"].iloc[0]
    )

    check(
        np.isclose(
            first_recursive,
            one_hour["predicted_demand_mw"],
            rtol=0,
            atol=1e-6,
        ),
        "First prediction matches one-hour model",
    )

    # Test 4: All predictions are finite and positive
    predictions = forecast[
        "predicted_demand_mw"
    ].to_numpy(dtype=float)

    check(
        np.isfinite(predictions).all()
        and (predictions > 0).all(),
        "All predictions are finite and positive",
    )

    # Test 5: Future actual demand cannot affect results
    future_times = pd.date_range(
        start=ISSUE_TIME,
        periods=24,
        freq="h",
    )

    future_data = pd.DataFrame({
        "hour_start_utc": future_times,
        "actual_load_mw": np.linspace(
            50000,
            100000,
            24,
        ),
    })

    contaminated_history = pd.concat(
        [historical, future_data],
        ignore_index=True,
    )

    forecast_with_future = forecast_multiple_hours(
        issue_time=ISSUE_TIME,
        horizon=HORIZON,
        historical_data=contaminated_history,
    )

    check(
        np.allclose(
            predictions,
            forecast_with_future[
                "predicted_demand_mw"
            ].to_numpy(dtype=float),
            rtol=0,
            atol=1e-6,
        ),
        "Future actual demand does not affect forecasts",
    )

    # Test 6: Incomplete recent history is rejected
    incomplete_history = historical.iloc[:-1].copy()

    try:
        forecast_multiple_hours(
            issue_time=ISSUE_TIME,
            horizon=HORIZON,
            historical_data=incomplete_history,
        )
    except ValueError:
        print(
            "PASS — Missing latest observation rejected"
        )
    else:
        raise AssertionError(
            "Missing latest observation was accepted."
        )

    # Test 7: Forecast steps are correctly numbered
    check(
        forecast["step"].tolist()
        == list(range(1, 25)),
        "Forecast steps numbered 1 through 24",
    )

    # Test 8: Original historical data is unchanged
    check(
        historical["hour_start_utc"].max()
        == ISSUE_TIME - pd.Timedelta(hours=1),
        "Original historical data remains unchanged",
    )

    print("\nFORECAST SUMMARY")
    print(f"Forecast hours: {len(forecast)}")
    print(
        f"Average demand: "
        f"{predictions.mean():,.2f} MW"
    )
    print(
        f"Minimum demand: "
        f"{predictions.min():,.2f} MW"
    )
    print(
        f"Maximum demand: "
        f"{predictions.max():,.2f} MW"
    )

    print(
        "\nALL RECURSIVE FORECAST TESTS PASSED"
    )


if __name__ == "__main__":
    main()
