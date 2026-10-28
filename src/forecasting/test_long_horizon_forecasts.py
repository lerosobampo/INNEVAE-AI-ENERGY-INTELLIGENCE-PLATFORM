
import time

import numpy as np
import pandas as pd

from multi_hour_forecast import forecast_multiple_hours
from one_hour_forecast import load_historical_data


ISSUE_TIME = pd.Timestamp(
    "2026-10-01T00:00:00+00:00"
)

HORIZONS = {
    "24h": 24,
    "7d": 168,
    "30d": 720,
}


def validate_forecast(forecast, horizon, expected_hours):
    if len(forecast) != expected_hours:
        raise AssertionError(
            f"{horizon}: expected {expected_hours} rows, "
            f"received {len(forecast)}"
        )

    expected_times = pd.date_range(
        start=ISSUE_TIME,
        periods=expected_hours,
        freq="h",
    )

    actual_times = pd.DatetimeIndex(
        pd.to_datetime(
            forecast["forecast_time_utc"],
            utc=True,
        )
    )

    if not actual_times.equals(expected_times):
        raise AssertionError(
            f"{horizon}: incorrect forecast timestamps"
        )

    if forecast["step"].tolist() != list(
        range(1, expected_hours + 1)
    ):
        raise AssertionError(
            f"{horizon}: incorrect step numbering"
        )

    values = forecast[
        "predicted_demand_mw"
    ].to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise AssertionError(
            f"{horizon}: non-finite predictions"
        )

    if not (values > 0).all():
        raise AssertionError(
            f"{horizon}: non-positive predictions"
        )

    return values


def main():
    print("\nINNEVA.E — Long-Horizon Forecast Tests")
    print("--------------------------------------")

    historical = load_historical_data()

    results = {}

    for horizon, expected_hours in HORIZONS.items():
        print(f"\nTesting horizon: {horizon}")

        start = time.perf_counter()

        forecast = forecast_multiple_hours(
            issue_time=ISSUE_TIME,
            horizon=horizon,
            historical_data=historical,
        )

        elapsed = time.perf_counter() - start

        values = validate_forecast(
            forecast,
            horizon,
            expected_hours,
        )

        results[horizon] = values

        print(
            f"PASS — {expected_hours} predictions generated"
        )
        print("PASS — Timestamps and steps validated")
        print("PASS — All predictions finite and positive")

        print(f"Average demand: {values.mean():,.2f} MW")
        print(f"Minimum demand: {values.min():,.2f} MW")
        print(f"Maximum demand: {values.max():,.2f} MW")
        print(f"Execution time: {elapsed:.2f} seconds")

    # Longer forecasts must reproduce the exact same
    # initial predictions as shorter forecasts.
    if not np.allclose(
        results["24h"],
        results["7d"][:24],
        rtol=0,
        atol=1e-6,
    ):
        raise AssertionError(
            "7-day forecast differs from 24-hour "
            "forecast during the first 24 hours."
        )

    print(
        "\nPASS — 7-day forecast matches first 24 hours"
    )

    if not np.allclose(
        results["7d"],
        results["30d"][:168],
        rtol=0,
        atol=1e-6,
    ):
        raise AssertionError(
            "30-day forecast differs from 7-day "
            "forecast during the first 168 hours."
        )

    print(
        "PASS — 30-day forecast matches first 7 days"
    )

    print("\nALL LONG-HORIZON FORECAST TESTS PASSED")


if __name__ == "__main__":
    main()
