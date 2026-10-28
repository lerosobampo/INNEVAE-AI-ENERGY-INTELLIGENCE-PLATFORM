
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from forecast_request import (
    create_forecast_request,
    validate_historical_cutoff,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_FILE = (
    PROJECT_ROOT
    / "data/forecasting/energy_intelligence_hourly.csv"
)

MODEL_FILE = (
    PROJECT_ROOT
    / "models/historical_demand_final.joblib"
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


def load_historical_data():
    """
    Load historical electricity demand observations.
    """

    df = pd.read_csv(DATA_FILE)

    df["hour_start_utc"] = pd.to_datetime(
        df["hour_start_utc"],
        utc=True,
    )

    df = df.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    if df["hour_start_utc"].duplicated().any():
        raise ValueError(
            "Historical data contains duplicate timestamps."
        )

    return df


def build_prediction_features(history, issue_time):
    """
    Generate the ten features expected by the
    historical demand forecasting model.

    Only observations before the forecast issue
    time are permitted.
    """

    issue_time = pd.Timestamp(issue_time)

    if issue_time.tzinfo is None:
        raise ValueError(
            "Forecast issue time must include a timezone."
        )

    issue_time = issue_time.tz_convert("UTC")

    history = history.copy()

    history["hour_start_utc"] = pd.to_datetime(
        history["hour_start_utc"],
        utc=True,
    )

    history = history[
        history["hour_start_utc"] < issue_time
    ].sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    if len(history) < 168:
        raise ValueError(
            "At least 168 historical hours are required."
        )

    expected_latest = (
        issue_time - pd.Timedelta(hours=1)
    )

    latest = history["hour_start_utc"].iloc[-1]

    if latest != expected_latest:
        raise ValueError(
            f"Latest observation is {latest}, "
            f"but expected {expected_latest}."
        )

    recent = history.tail(168).copy()

    expected_timestamps = pd.date_range(
        end=expected_latest,
        periods=168,
        freq="h",
    )

    if not recent["hour_start_utc"].reset_index(
        drop=True
    ).equals(pd.Series(expected_timestamps)):
        raise ValueError(
            "Historical demand does not contain "
            "168 consecutive hourly observations."
        )

    demand = pd.to_numeric(
        recent["actual_load_mw"],
        errors="coerce",
    )

    if demand.isna().any():
        raise ValueError(
            "Historical demand contains missing values."
        )

    if not np.isfinite(demand.to_numpy()).all():
        raise ValueError(
            "Historical demand contains non-finite values."
        )

    features = {
        "hour_of_day": issue_time.hour,
        "day_of_week": issue_time.day_of_week,
        "month": issue_time.month,
        "is_weekend": int(
            issue_time.day_of_week >= 5
        ),
        "demand_lag_1h": demand.iloc[-1],
        "demand_lag_24h": demand.iloc[-24],
        "demand_lag_168h": demand.iloc[-168],
        "demand_rolling_mean_24h": (
            demand.iloc[-24:].mean()
        ),
        "demand_rolling_mean_168h": (
            demand.mean()
        ),
        "demand_rolling_std_24h": (
            demand.iloc[-24:].std()
        ),
    }

    feature_df = pd.DataFrame(
        [features],
        columns=EXPECTED_FEATURES,
    )

    if feature_df.isna().any().any():
        raise ValueError(
            "Generated features contain missing values."
        )

    return feature_df


def forecast_one_hour(issue_time):
    """
    Generate a one-hour electricity demand forecast.
    """

    request = create_forecast_request(
        issue_time=issue_time,
        horizon="1h",
    )

    historical = load_historical_data()

    history = historical[
        historical["hour_start_utc"]
        < request.issue_time_utc
    ].copy()

    validate_historical_cutoff(
        history,
        request,
    )

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Trained model not found: {MODEL_FILE}"
        )

    model_artifact = joblib.load(MODEL_FILE)

    model = model_artifact["model"]
    model_features = model_artifact["features"]

    features = build_prediction_features(
        history,
        request.issue_time_utc,
    )

    missing_features = (
        set(model_features) - set(features.columns)
    )

    if missing_features:
        raise ValueError(
            f"Missing model features: {missing_features}"
        )

    prediction = model.predict(
        features[model_features].astype(float)
    )[0]

    if not np.isfinite(prediction):
        raise ValueError(
            "Model produced a non-finite prediction."
        )

    return {
        "issue_time_utc": request.issue_time_utc,
        "forecast_start_utc": request.forecast_start_utc,
        "forecast_end_utc": request.forecast_end_utc,
        "forecast_horizon": request.horizon,
        "predicted_demand_mw": float(prediction),
        "last_observed_demand_mw": float(
            features["demand_lag_1h"].iloc[0]
        ),
    }


def main():
    issue_time = "2026-10-01T00:00:00+00:00"

    print("\nINNEVA.E — One-Hour Demand Forecast")

    result = forecast_one_hour(issue_time)

    for key, value in result.items():
        print(f"{key}: {value}")

    print("\nFORECAST COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
