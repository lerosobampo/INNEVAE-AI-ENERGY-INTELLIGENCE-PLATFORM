
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data/development/demand_features_90d.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/historical_ml"
)

MODEL_DIR = PROJECT_ROOT / "models"

FEATURES = [
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

TARGET = "actual_load_mw"


def calculate_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))

    nonzero = actual != 0
    mape = (
        np.mean(
            np.abs(
                (actual[nonzero] - predicted[nonzero])
                / actual[nonzero]
            )
        ) * 100
        if nonzero.any()
        else np.nan
    )

    return {
        "mae_mw": mae,
        "rmse_mw": rmse,
        "mape_pct": mape,
    }


def main():
    print("\nINNEVA.E — Historical Demand ML Training")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["hour_start_utc"]
    )

    df = df.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    # Remove rows without sufficient historical demand.
    df = df.dropna(
        subset=FEATURES + [TARGET]
    ).reset_index(drop=True)

    # Chronological split: 80% training, 20% validation.
    split_index = int(len(df) * 0.80)

    train = df.iloc[:split_index].copy()
    validation = df.iloc[split_index:].copy()

    X_train = train[FEATURES].astype(float)
    y_train = train[TARGET]

    X_validation = validation[FEATURES].astype(float)
    y_validation = validation[TARGET]

    model = HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=42
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_validation)

    # Evaluate the persistence baseline on the exact
    # same validation timestamps.
    persistence_predictions = (
        validation["demand_lag_1h"].to_numpy()
    )

    ml_metrics = calculate_metrics(
        y_validation,
        predictions
    )

    baseline_metrics = calculate_metrics(
        y_validation,
        persistence_predictions
    )

    metrics_df = pd.DataFrame([
        {
            "model": "HistGradientBoosting",
            **ml_metrics
        },
        {
            "model": "Persistence (1h)",
            **baseline_metrics
        }
    ])

    improvement = (
        (baseline_metrics["mae_mw"] - ml_metrics["mae_mw"])
        / baseline_metrics["mae_mw"]
    ) * 100

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    metrics_df.to_csv(
        OUTPUT_DIR / "model_metrics.csv",
        index=False
    )

    prediction_df = pd.DataFrame({
        "hour_start_utc": validation["hour_start_utc"],
        "actual_load_mw": y_validation,
        "ml_prediction_mw": predictions,
        "persistence_prediction_mw": persistence_predictions
    })

    prediction_df.to_csv(
        OUTPUT_DIR / "model_predictions.csv",
        index=False
    )

    model_path = MODEL_DIR / "historical_demand_model.joblib"

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "target": TARGET,
            "forecast_horizon_hours": 1,
            "validation_start_utc": str(
                validation["hour_start_utc"].iloc[0]
            ),
        },
        model_path
    )

    print(f"\nTotal usable records: {len(df):,}")
    print(f"Training records: {len(train):,}")
    print(f"Validation records: {len(validation):,}")

    print("\nModel comparison:")
    print(metrics_df.to_string(index=False))

    print(
        f"\nML MAE improvement vs persistence: "
        f"{improvement:.2f}%"
    )

    print(f"\nModel saved to: {model_path}")
    print(f"Results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
