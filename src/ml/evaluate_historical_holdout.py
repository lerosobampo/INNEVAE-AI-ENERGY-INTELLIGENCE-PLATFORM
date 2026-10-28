
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data/forecasting/energy_intelligence_hourly.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/historical_holdout"
)

MODEL_FILE = (
    PROJECT_ROOT
    / "models/historical_demand_final.joblib"
)

HOLDOUT_START = pd.Timestamp(
    "2026-07-01",
    tz="UTC"
)

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


def build_features(df):
    df = df.copy()

    df["hour_start_utc"] = pd.to_datetime(
        df["hour_start_utc"],
        utc=True
    )

    df = df.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    assert df["hour_start_utc"].is_unique, (
        "Duplicate timestamps detected."
    )

    assert df["hour_start_utc"].diff().dropna().eq(
        pd.Timedelta(hours=1)
    ).all(), "Hourly continuity check failed."

    target = df[TARGET]

    df["demand_lag_1h"] = target.shift(1)
    df["demand_lag_24h"] = target.shift(24)
    df["demand_lag_168h"] = target.shift(168)

    previous = target.shift(1)

    df["demand_rolling_mean_24h"] = (
        previous.rolling(24).mean()
    )

    df["demand_rolling_mean_168h"] = (
        previous.rolling(168).mean()
    )

    df["demand_rolling_std_24h"] = (
        previous.rolling(24).std()
    )

    return df


def main():
    print("\nINNEVA.E — Final Historical Holdout Evaluation")

    df = pd.read_csv(INPUT_FILE)
    df = build_features(df)

    train = df[
        df["hour_start_utc"] < HOLDOUT_START
    ].copy()

    holdout = df[
        df["hour_start_utc"] >= HOLDOUT_START
    ].copy()

    train = train.dropna(
        subset=FEATURES + [TARGET]
    )

    holdout = holdout.dropna(
        subset=FEATURES + [TARGET]
    )

    assert len(train) > 0, "Training dataset is empty."
    assert len(holdout) > 0, "Holdout dataset is empty."

    assert train["hour_start_utc"].max() < (
        holdout["hour_start_utc"].min()
    ), "Training and holdout periods overlap."

    print(f"\nTraining records: {len(train):,}")
    print(f"Holdout records: {len(holdout):,}")

    print(
        "Training ends:",
        train["hour_start_utc"].max()
    )

    print(
        "Holdout starts:",
        holdout["hour_start_utc"].min()
    )

    model = HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=42
    )

    model.fit(
        train[FEATURES].astype(float),
        train[TARGET]
    )

    ml_predictions = model.predict(
        holdout[FEATURES].astype(float)
    )

    persistence_predictions = (
        holdout["demand_lag_1h"].to_numpy()
    )

    ml_metrics = calculate_metrics(
        holdout[TARGET],
        ml_predictions
    )

    persistence_metrics = calculate_metrics(
        holdout[TARGET],
        persistence_predictions
    )

    improvement = (
        (
            persistence_metrics["mae_mw"]
            - ml_metrics["mae_mw"]
        )
        / persistence_metrics["mae_mw"]
    ) * 100

    metrics = pd.DataFrame([
        {
            "model": "HistGradientBoosting",
            **ml_metrics,
        },
        {
            "model": "Persistence (1h)",
            **persistence_metrics,
        },
    ])

    predictions = pd.DataFrame({
        "hour_start_utc": holdout["hour_start_utc"],
        "actual_load_mw": holdout[TARGET],
        "ml_prediction_mw": ml_predictions,
        "persistence_prediction_mw": persistence_predictions,
    })

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    metrics.to_csv(
        OUTPUT_DIR / "holdout_metrics.csv",
        index=False
    )

    predictions.to_csv(
        OUTPUT_DIR / "holdout_predictions.csv",
        index=False
    )

    # Save separately; preserve the existing model.
    MODEL_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if MODEL_FILE.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing model: {MODEL_FILE}"
        )

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "target": TARGET,
            "forecast_horizon_hours": 1,
            "training_end_utc": str(
                train["hour_start_utc"].max()
            ),
            "holdout_start_utc": str(HOLDOUT_START),
        },
        MODEL_FILE
    )

    print("\nMODEL COMPARISON")
    print(metrics.to_string(index=False))

    print(
        f"\nML MAE improvement vs persistence: "
        f"{improvement:.2f}%"
    )

    print(f"\nModel saved to: {MODEL_FILE}")
    print(f"Results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
