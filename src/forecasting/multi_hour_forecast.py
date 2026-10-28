
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from forecast_request import create_forecast_request
from one_hour_forecast import (
    load_historical_data,
    build_prediction_features,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_FILE = (
    PROJECT_ROOT
    / "models/historical_demand_final.joblib"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/multi_hour_forecasting"
)


def forecast_multiple_hours(
    issue_time,
    horizon="24h",
    historical_data=None,
):
    """
    Generate recursive electricity demand forecasts.

    Predictions are appended to the historical series,
    allowing subsequent hours to use previous forecasts.

    Future actual demand is never used.
    """

    request = create_forecast_request(
        issue_time=issue_time,
        horizon=horizon,
    )

    if historical_data is None:
        historical = load_historical_data()
    else:
        historical = historical_data.copy()

    historical["hour_start_utc"] = pd.to_datetime(
        historical["hour_start_utc"],
        utc=True,
    )

    historical = historical[
        historical["hour_start_utc"]
        < request.issue_time_utc
    ].copy()

    historical = historical.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Trained model not found: {MODEL_FILE}"
        )

    artifact = joblib.load(MODEL_FILE)

    model = artifact["model"]
    feature_names = artifact["features"]

    working_history = historical[
        ["hour_start_utc", "actual_load_mw"]
    ].copy()

    predictions = []

    for step in range(request.horizon_hours):

        forecast_time = (
            request.issue_time_utc
            + pd.Timedelta(hours=step)
        )

        features = build_prediction_features(
            working_history,
            forecast_time,
        )

        predicted_mw = float(
            model.predict(
                features[feature_names].astype(float)
            )[0]
        )

        if not np.isfinite(predicted_mw):
            raise ValueError(
                f"Non-finite prediction at {forecast_time}"
            )

        predictions.append({
            "issue_time_utc": request.issue_time_utc,
            "forecast_time_utc": forecast_time,
            "horizon": request.horizon,
            "step": step + 1,
            "predicted_demand_mw": predicted_mw,
        })

        # Append the predicted value, not future actual demand.
        next_observation = pd.DataFrame({
            "hour_start_utc": [forecast_time],
            "actual_load_mw": [predicted_mw],
        })

        working_history = pd.concat(
            [working_history, next_observation],
            ignore_index=True,
        )

    return pd.DataFrame(predictions)


def main():
    issue_time = "2026-10-01T00:00:00+00:00"

    print("\nINNEVA.E — Multi-Hour Demand Forecast")

    forecast = forecast_multiple_hours(
        issue_time=issue_time,
        horizon="24h",
    )

    print("\nFORECAST RESULTS:")
    print(forecast.to_string(index=False))

    print("\nFORECAST SUMMARY:")
    print(
        f"Forecast hours: {len(forecast)}"
    )
    print(
        f"Average demand: "
        f"{forecast['predicted_demand_mw'].mean():,.2f} MW"
    )
    print(
        f"Minimum demand: "
        f"{forecast['predicted_demand_mw'].min():,.2f} MW"
    )
    print(
        f"Maximum demand: "
        f"{forecast['predicted_demand_mw'].max():,.2f} MW"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        OUTPUT_DIR
        / "forecast_24h_2026-10-01.csv"
    )

    forecast.to_csv(
        output_file,
        index=False,
    )

    print(f"\nForecast saved to: {output_file}")
    print("\n24-HOUR FORECAST COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
