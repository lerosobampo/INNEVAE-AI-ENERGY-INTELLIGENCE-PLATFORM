
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

RECURSIVE_MODEL_FILE = (
    PROJECT_ROOT / "models/historical_demand_final.joblib"
)

DIRECT_MODEL_FILE = (
    PROJECT_ROOT / "models/direct_demand_final.joblib"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/unified_forecasting"
)

SUPPORTED_METHODS = [
    "auto",
    "recursive_ml",
    "direct_ml",
    "daily_naive",
    "weekly_naive",
]

AUTO_METHODS = {
    "1h": "recursive_ml",
    "24h": "recursive_ml",
    "7d": "recursive_ml",
    "30d": "direct_ml",
}

RECURSIVE_FEATURES = [
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

DIRECT_FEATURES = [
    "lead_hours",
    "target_hour",
    "target_day_of_week",
    "target_month",
    "target_is_weekend",
    "seasonal_daily_mw",
    "seasonal_weekly_mw",
    "issue_hour",
    "issue_day_of_week",
    "issue_month",
    "issue_lag_1h",
    "issue_lag_24h",
    "issue_lag_168h",
    "issue_mean_24h",
    "issue_mean_168h",
    "issue_std_24h",
]


def prepare_history(historical_data, issue_time):
    """
    Keep observations strictly before issue_time.

    Require a continuous 168-hour history immediately
    preceding the requested forecast issue.
    """

    if historical_data is None:
        historical = load_historical_data()
    else:
        historical = historical_data.copy()

    required = {
        "hour_start_utc",
        "actual_load_mw",
    }

    if not required.issubset(historical.columns):
        raise ValueError(
            "Historical data must contain "
            "hour_start_utc and actual_load_mw."
        )

    historical["hour_start_utc"] = pd.to_datetime(
        historical["hour_start_utc"],
        utc=True,
        errors="raise",
    )

    if historical["hour_start_utc"].isna().any():
        raise ValueError(
            "Historical timestamps contain missing values."
        )

    historical["actual_load_mw"] = pd.to_numeric(
        historical["actual_load_mw"],
        errors="raise",
    )

    historical = historical[
        historical["hour_start_utc"] < issue_time
    ].copy()

    historical = historical.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    if historical["hour_start_utc"].duplicated().any():
        raise ValueError(
            "Historical timestamps contain duplicates."
        )

    if len(historical) < 168:
        raise ValueError(
            "At least 168 hours of history are required."
        )

    recent = historical.tail(168).copy()

    expected = pd.date_range(
        end=issue_time - pd.Timedelta(hours=1),
        periods=168,
        freq="h",
    )

    if not pd.DatetimeIndex(
        recent["hour_start_utc"]
    ).equals(expected):
        raise ValueError(
            "The 168 hours immediately before the "
            "forecast issue must be continuous."
        )

    if not np.isfinite(
        recent["actual_load_mw"].to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Recent historical demand contains invalid values."
        )

    if (
        recent["actual_load_mw"] <= 0
    ).any():
        raise ValueError(
            "Recent historical demand must be positive."
        )

    return historical[
        ["hour_start_utc", "actual_load_mw"]
    ].copy()


def load_model(path, expected_features):
    if not path.exists():
        raise FileNotFoundError(
            f"Model not found: {path}"
        )

    artifact = joblib.load(path)

    if not isinstance(artifact, dict):
        raise ValueError(
            "Invalid model artifact."
        )

    if "model" not in artifact or "features" not in artifact:
        raise ValueError(
            "Model artifact is missing required fields."
        )

    if list(artifact["features"]) != expected_features:
        raise ValueError(
            "Model features do not match the "
            "unified engine specification."
        )

    return artifact


def make_daily_naive(history, issue_time, hours):
    """
    Repeat the last fully observed 24-hour pattern.
    """

    demand = history.set_index(
        "hour_start_utc"
    )["actual_load_mw"]

    reference_start = (
        issue_time - pd.Timedelta(hours=24)
    )

    pattern_times = pd.date_range(
        start=reference_start,
        periods=24,
        freq="h",
    )

    pattern = demand.loc[
        pattern_times
    ].to_numpy(dtype=float)

    return np.resize(pattern, hours)


def make_weekly_naive(history, issue_time, hours):
    """
    Repeat the last fully observed 168-hour pattern.
    """

    demand = history.set_index(
        "hour_start_utc"
    )["actual_load_mw"]

    reference_start = (
        issue_time - pd.Timedelta(hours=168)
    )

    pattern_times = pd.date_range(
        start=reference_start,
        periods=168,
        freq="h",
    )

    pattern = demand.loc[
        pattern_times
    ].to_numpy(dtype=float)

    return np.resize(pattern, hours)


def make_recursive_forecast(
    history,
    issue_time,
    hours,
):
    artifact = load_model(
        RECURSIVE_MODEL_FILE,
        RECURSIVE_FEATURES,
    )

    model = artifact["model"]

    training_end = pd.Timestamp(
        artifact["training_end_utc"]
    )

    if training_end.tzinfo is None:
        raise ValueError(
            "Recursive model training timestamp "
            "must include a timezone."
        )

    training_end = training_end.tz_convert("UTC")

    if issue_time <= training_end:
        raise ValueError(
            "Forecast issue must be after the "
            "recursive model training period."
        )

    working = history.copy()

    predictions = []

    for step in range(hours):
        target_time = (
            issue_time + pd.Timedelta(hours=step)
        )

        features = build_prediction_features(
            working,
            target_time,
        )

        prediction = float(
            model.predict(
                features[RECURSIVE_FEATURES].astype(float)
            )[0]
        )

        if not np.isfinite(prediction):
            raise ValueError(
                "Recursive model produced a "
                "non-finite prediction."
            )

        if prediction <= 0:
            raise ValueError(
                "Recursive model produced "
                "non-positive demand."
            )

        predictions.append(prediction)

        working = pd.concat(
            [
                working,
                pd.DataFrame({
                    "hour_start_utc": [target_time],
                    "actual_load_mw": [prediction],
                }),
            ],
            ignore_index=True,
        )

    return np.asarray(
        predictions,
        dtype=float,
    )


def make_direct_forecast(
    history,
    issue_time,
    hours,
):
    artifact = load_model(
        DIRECT_MODEL_FILE,
        DIRECT_FEATURES,
    )

    if hours > artifact["maximum_horizon_hours"]:
        raise ValueError(
            "Requested horizon exceeds "
            "direct model capability."
        )

    training_end = pd.Timestamp(
        artifact["training_target_end_utc"]
    )

    if training_end.tzinfo is None:
        raise ValueError(
            "Direct model training timestamp "
            "must include a timezone."
        )

    training_end = training_end.tz_convert("UTC")

    if issue_time <= training_end:
        raise ValueError(
            "Forecast issue must be after the "
            "direct model training period."
        )

    recent = history.tail(168).copy()

    demand = recent["actual_load_mw"].to_numpy(
        dtype=float
    )

    daily_pattern = demand[-24:]
    weekly_pattern = demand[-168:]

    rows = []

    for step in range(hours):
        target_time = (
            issue_time + pd.Timedelta(hours=step)
        )

        rows.append({
            "lead_hours": step + 1,
            "target_hour": target_time.hour,
            "target_day_of_week": (
                target_time.day_of_week
            ),
            "target_month": target_time.month,
            "target_is_weekend": int(
                target_time.day_of_week >= 5
            ),
            "seasonal_daily_mw": (
                daily_pattern[step % 24]
            ),
            "seasonal_weekly_mw": (
                weekly_pattern[step % 168]
            ),
            "issue_hour": issue_time.hour,
            "issue_day_of_week": (
                issue_time.day_of_week
            ),
            "issue_month": issue_time.month,
            "issue_lag_1h": demand[-1],
            "issue_lag_24h": demand[-24],
            "issue_lag_168h": demand[-168],
            "issue_mean_24h": (
                daily_pattern.mean()
            ),
            "issue_mean_168h": (
                weekly_pattern.mean()
            ),
            "issue_std_24h": (
                daily_pattern.std(ddof=1)
            ),
        })

    features = pd.DataFrame(rows)

    predictions = artifact["model"].predict(
        features[DIRECT_FEATURES].astype(float)
    )

    return np.asarray(
        predictions,
        dtype=float,
    )


def forecast(
    issue_time,
    horizon="24h",
    method="auto",
    historical_data=None,
):
    """
    Unified electricity demand forecasting API.

    Parameters
    ----------
    issue_time:
        Timezone-aware, hour-aligned forecast issue.

    horizon:
        One of: 1h, 24h, 7d, 30d.

    method:
        auto, recursive_ml, direct_ml,
        daily_naive, weekly_naive.

    historical_data:
        Optional historical DataFrame for testing
        or offline backtesting.

    Returns
    -------
    pandas.DataFrame:
        Standardized hourly demand forecast.
    """

    request = create_forecast_request(
        issue_time=issue_time,
        horizon=horizon,
    )

    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f"Unsupported method: {method}. "
            f"Choose from {SUPPORTED_METHODS}"
        )

    selected_method = (
        AUTO_METHODS[horizon]
        if method == "auto"
        else method
    )

    history = prepare_history(
        historical_data,
        request.issue_time_utc,
    )

    hours = request.horizon_hours

    if selected_method == "recursive_ml":
        predictions = make_recursive_forecast(
            history,
            request.issue_time_utc,
            hours,
        )

    elif selected_method == "direct_ml":
        predictions = make_direct_forecast(
            history,
            request.issue_time_utc,
            hours,
        )

    elif selected_method == "daily_naive":
        predictions = make_daily_naive(
            history,
            request.issue_time_utc,
            hours,
        )

    elif selected_method == "weekly_naive":
        predictions = make_weekly_naive(
            history,
            request.issue_time_utc,
            hours,
        )

    else:
        raise ValueError(
            "Unknown forecasting method."
        )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    if len(predictions) != hours:
        raise ValueError(
            "Forecast returned an incorrect "
            "number of hourly predictions."
        )

    if not np.isfinite(predictions).all():
        raise ValueError(
            "Forecast contains non-finite values."
        )

    if (predictions <= 0).any():
        raise ValueError(
            "Forecast contains non-positive demand."
        )

    forecast_times = pd.date_range(
        start=request.forecast_start_utc,
        periods=hours,
        freq="h",
    )

    result = pd.DataFrame({
        "issue_time_utc": request.issue_time_utc,
        "forecast_time_utc": forecast_times,
        "horizon": horizon,
        "requested_method": method,
        "selected_method": selected_method,
        "step": np.arange(1, hours + 1),
        "predicted_demand_mw": predictions,
    })

    return result


def main():
    print(
        "\nINNEVA.E — Unified Forecast Engine"
    )
    print("----------------------------------")

    issue_time = "2026-10-01T00:00:00+00:00"

    scenarios = [
        ("1h", "auto"),
        ("24h", "auto"),
        ("7d", "auto"),
        ("30d", "auto"),
    ]

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for horizon, method in scenarios:
        print(
            f"\nGENERATING {horizon.upper()} FORECAST"
        )

        result = forecast(
            issue_time=issue_time,
            horizon=horizon,
            method=method,
        )

        selected = result[
            "selected_method"
        ].iloc[0]

        print(f"Selected method: {selected}")
        print(f"Forecast hours: {len(result)}")

        print(
            "Average demand: "
            f"{result['predicted_demand_mw'].mean():,.2f} MW"
        )

        print(
            "Minimum demand: "
            f"{result['predicted_demand_mw'].min():,.2f} MW"
        )

        print(
            "Maximum demand: "
            f"{result['predicted_demand_mw'].max():,.2f} MW"
        )

        print("\nFIRST THREE PREDICTIONS")

        print(
            result[
                [
                    "forecast_time_utc",
                    "predicted_demand_mw",
                ]
            ].head(3).to_string(index=False)
        )

        output_file = (
            OUTPUT_DIR
            / f"forecast_{horizon}_2026-10-01.csv"
        )

        if output_file.exists():
            raise FileExistsError(
                "Output already exists; refusing "
                f"to overwrite: {output_file}"
            )

        result.to_csv(
            output_file,
            index=False,
        )

        print(f"\nSaved to: {output_file}")

    print(
        "\nUNIFIED FORECAST ENGINE "
        "COMPLETED SUCCESSFULLY"
    )


if __name__ == "__main__":
    main()
