
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor

from one_hour_forecast import (
    load_historical_data,
    build_prediction_features,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DIRECT_MODEL_FILE = (
    PROJECT_ROOT / "models/direct_demand_model.joblib"
)

DIRECT_VALIDATION_FILE = (
    PROJECT_ROOT
    / "data/processed/direct_forecasting/validation"
    / "validation_predictions.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/architecture_comparison"
)

TRAINING_CUTOFF = pd.Timestamp(
    "2026-03-01T00:00:00+00:00"
)

HORIZONS = {
    "24h": 24,
    "7d": 168,
    "30d": 720,
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


def calculate_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    errors = actual - predicted

    return {
        "mae_mw": float(np.mean(np.abs(errors))),
        "rmse_mw": float(
            np.sqrt(np.mean(errors ** 2))
        ),
        "mape_pct": float(
            np.mean(
                np.abs(errors / actual)
            ) * 100
        ),
    }


def build_recursive_training_data(historical):
    """
    Recreate the one-hour feature definitions
    using only pre-cutoff demand observations.
    """

    df = historical[
        historical["hour_start_utc"] < TRAINING_CUTOFF
    ].copy()

    df = df.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    demand = df["actual_load_mw"]

    timestamps = df["hour_start_utc"]

    df["hour_of_day"] = timestamps.dt.hour
    df["day_of_week"] = timestamps.dt.dayofweek
    df["month"] = timestamps.dt.month

    df["is_weekend"] = (
        df["day_of_week"] >= 5
    ).astype(int)

    df["demand_lag_1h"] = demand.shift(1)
    df["demand_lag_24h"] = demand.shift(24)
    df["demand_lag_168h"] = demand.shift(168)

    shifted = demand.shift(1)

    df["demand_rolling_mean_24h"] = (
        shifted.rolling(24).mean()
    )

    df["demand_rolling_mean_168h"] = (
        shifted.rolling(168).mean()
    )

    df["demand_rolling_std_24h"] = (
        shifted.rolling(24).std()
    )

    training = df.dropna(
        subset=RECURSIVE_FEATURES + ["actual_load_mw"]
    ).copy()

    if training.empty:
        raise ValueError(
            "Recursive training dataset is empty."
        )

    if training["hour_start_utc"].max() >= (
        TRAINING_CUTOFF
    ):
        raise AssertionError(
            "Recursive training includes validation data."
        )

    return training


def train_recursive_model(historical):
    print("\nTRAINING MATCHED RECURSIVE MODEL")

    training = build_recursive_training_data(
        historical
    )

    model = HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=42,
    )

    model.fit(
        training[RECURSIVE_FEATURES],
        training["actual_load_mw"],
    )

    print(
        f"Training examples: {len(training):,}"
    )
    print(
        f"Latest training observation: "
        f"{training['hour_start_utc'].max()}"
    )

    return model


def recursive_forecast(
    model,
    historical,
    issue_time,
    hours,
):
    """
    Generate recursive forecasts using a model
    trained before the validation period.
    """

    working = historical.loc[
        historical["hour_start_utc"] < issue_time,
        ["hour_start_utc", "actual_load_mw"],
    ].copy()

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
                features[RECURSIVE_FEATURES]
            )[0]
        )

        if not np.isfinite(prediction):
            raise ValueError(
                "Recursive model produced invalid output."
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


def main():
    print(
        "\nINNEVA.E — Forecast Architecture Comparison"
    )
    print("-------------------------------------------")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    historical = load_historical_data()

    recursive_model = train_recursive_model(
        historical
    )

    if not DIRECT_MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Missing direct model: {DIRECT_MODEL_FILE}"
        )

    if not DIRECT_VALIDATION_FILE.exists():
        raise FileNotFoundError(
            "Missing direct validation predictions."
        )

    direct_artifact = joblib.load(
        DIRECT_MODEL_FILE
    )

    if direct_artifact.get(
        "training_target_end_utc"
    ) is None:
        raise ValueError(
            "Direct model metadata is incomplete."
        )

    direct_training_end = pd.Timestamp(
        direct_artifact["training_target_end_utc"]
    )

    if direct_training_end >= TRAINING_CUTOFF:
        raise AssertionError(
            "Direct model trained on validation targets."
        )

    direct_validation = pd.read_csv(
        DIRECT_VALIDATION_FILE
    )

    direct_validation["issue_time_utc"] = (
        pd.to_datetime(
            direct_validation["issue_time_utc"],
            utc=True,
        )
    )

    direct_validation["target_time_utc"] = (
        pd.to_datetime(
            direct_validation["target_time_utc"],
            utc=True,
        )
    )

    issue_times = sorted(
        direct_validation["issue_time_utc"].unique()
    )

    all_rows = []

    # Compute the longest recursive forecast once
    # for each issue time, then reuse its first
    # 24 or 168 predictions for shorter horizons.
    for index, issue_time in enumerate(
        issue_times,
        start=1,
    ):
        issue_time = pd.Timestamp(issue_time)

        start_time = time.perf_counter()

        issue_data = direct_validation[
            direct_validation["issue_time_utc"]
            == issue_time
        ].sort_values("lead_hours")

        if len(issue_data) != 720:
            raise ValueError(
                f"Expected 720 rows for {issue_time}"
            )

        recursive_values = recursive_forecast(
            recursive_model,
            historical,
            issue_time,
            hours=720,
        )

        result = issue_data[
            [
                "issue_time_utc",
                "target_time_utc",
                "lead_hours",
                "actual_load_mw",
                "direct_ml_mw",
                "seasonal_daily_mw",
                "seasonal_weekly_mw",
            ]
        ].copy()

        result["recursive_ml_mw"] = (
            recursive_values
        )

        all_rows.append(result)

        elapsed = time.perf_counter() - start_time

        print(
            f"Completed {index}/{len(issue_times)} "
            f"| {issue_time.date()} "
            f"| {elapsed:.2f}s"
        )

    predictions = pd.concat(
        all_rows,
        ignore_index=True,
    )

    models = {
        "Recursive ML": "recursive_ml_mw",
        "Direct ML": "direct_ml_mw",
        "Seasonal Naive 24h": "seasonal_daily_mw",
        "Seasonal Naive 168h": "seasonal_weekly_mw",
    }

    metric_rows = []
    issue_metric_rows = []

    for horizon, hours in HORIZONS.items():
        subset = predictions[
            predictions["lead_hours"] <= hours
        ]

        for name, column in models.items():
            metrics = calculate_metrics(
                subset["actual_load_mw"],
                subset[column],
            )

            metric_rows.append({
                "horizon": horizon,
                "model": name,
                "forecast_origins": subset[
                    "issue_time_utc"
                ].nunique(),
                "evaluated_hours": len(subset),
                **metrics,
            })

        for issue_time, group in subset.groupby(
            "issue_time_utc"
        ):
            for name, column in models.items():
                metrics = calculate_metrics(
                    group["actual_load_mw"],
                    group[column],
                )

                issue_metric_rows.append({
                    "horizon": horizon,
                    "issue_time_utc": issue_time,
                    "model": name,
                    **metrics,
                })

    metrics_df = pd.DataFrame(metric_rows)
    issue_metrics_df = pd.DataFrame(
        issue_metric_rows
    )

    predictions.to_csv(
        OUTPUT_DIR / "comparison_predictions.csv",
        index=False,
    )

    metrics_df.to_csv(
        OUTPUT_DIR / "comparison_metrics.csv",
        index=False,
    )

    issue_metrics_df.to_csv(
        OUTPUT_DIR / "comparison_metrics_by_issue.csv",
        index=False,
    )

    for horizon in HORIZONS:
        print(f"\n{horizon.upper()} COMPARISON")

        subset = metrics_df[
            metrics_df["horizon"] == horizon
        ]

        print(
            subset[
                [
                    "model",
                    "mae_mw",
                    "rmse_mw",
                    "mape_pct",
                ]
            ].to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        winner = subset.loc[
            subset["mae_mw"].idxmin()
        ]

        print(
            f"Lowest MAE: {winner['model']} "
            f"({winner['mae_mw']:,.2f} MW)"
        )

    print("\nCOMPARISON SUMMARY")
    print(
        f"Forecast origins: "
        f"{predictions['issue_time_utc'].nunique()}"
    )
    print(
        f"Total 30-day predictions: "
        f"{len(predictions):,}"
    )

    print(f"\nResults saved to: {OUTPUT_DIR}")

    print(
        "\nARCHITECTURE COMPARISON COMPLETED SUCCESSFULLY"
    )


if __name__ == "__main__":
    main()
