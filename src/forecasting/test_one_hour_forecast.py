
import pandas as pd

from forecast_request import create_forecast_request
from one_hour_forecast import (
    load_historical_data,
    build_prediction_features,
    forecast_one_hour,
)


ISSUE_TIME = pd.Timestamp(
    "2026-10-01T00:00:00+00:00"
)

EXPECTED_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
    "demand_lag_1h",
    "demand_lag_24h",
    "demand_lag_168h",
    "demand_rolling_mean_24h",
    "demand_rolling_mean_168h",
    "demand_rolling_std_24h",
]


def main():
    print("\nINNEVA.E — One-Hour Forecast Tests")

    # Test 1: Forecast request
    request = create_forecast_request(
        ISSUE_TIME,
        horizon="1h",
    )

    assert request.horizon_hours == 1
    print("PASS — One-hour forecast request")

    # Test 2: Historical data
    history = load_historical_data()

    assert (
        history["hour_start_utc"].max()
        == ISSUE_TIME - pd.Timedelta(hours=1)
    )

    print("PASS — Historical data ends before forecast")

    # Test 3: Feature engineering
    features = build_prediction_features(
        history,
        ISSUE_TIME,
    )

    print("\nGENERATED FEATURE COLUMNS:")
    print(features.columns.tolist())

    print("\nNUMBER OF FEATURES:")
    print(len(features.columns))

    print("\nFEATURE VALUES:")
    print(features.to_string(index=False))

    missing = set(EXPECTED_FEATURES) - set(features.columns)
    extra = set(features.columns) - set(EXPECTED_FEATURES)

    assert not missing, f"Missing features: {sorted(missing)}"
    assert not extra, f"Unexpected features: {sorted(extra)}"
    assert len(features) == 1

    print("\nPASS — Feature schema validation")

    # Test 4: Historical lag features
    demand = history["actual_load_mw"]

    assert (
        features["demand_lag_1h"].iloc[0]
        == demand.iloc[-1]
    )

    assert (
        features["demand_lag_24h"].iloc[0]
        == demand.iloc[-24]
    )

    assert (
        features["demand_lag_168h"].iloc[0]
        == demand.iloc[-168]
    )

    print("PASS — Historical lag features")

    # Test 5: Rolling statistics
    expected_mean_24 = demand.iloc[-24:].mean()
    expected_mean_168 = demand.iloc[-168:].mean()
    expected_std_24 = demand.iloc[-24:].std()

    assert abs(
        features["demand_rolling_mean_24h"].iloc[0]
        - expected_mean_24
    ) < 1e-6

    assert abs(
        features["demand_rolling_mean_168h"].iloc[0]
        - expected_mean_168
    ) < 1e-6

    assert abs(
        features["demand_rolling_std_24h"].iloc[0]
        - expected_std_24
    ) < 1e-6

    print("PASS — Rolling demand statistics")

    # Test 6: Missing latest observation
    incomplete_history = history.iloc[:-1].copy()

    try:
        build_prediction_features(
            incomplete_history,
            ISSUE_TIME,
        )
    except ValueError:
        print("PASS — Missing latest observation rejected")
    else:
        raise AssertionError(
            "Missing historical observation was accepted."
        )

    # Test 7: Model inference
    result = forecast_one_hour(ISSUE_TIME)

    assert result["forecast_horizon"] == "1h"
    assert result["predicted_demand_mw"] > 0

    print("PASS — Model inference")

    print("\nPREDICTED DEMAND:")
    print(f"{result['predicted_demand_mw']:.2f} MW")

    print("\nALL ONE-HOUR FORECAST TESTS PASSED")


if __name__ == "__main__":
    main()
