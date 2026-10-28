
from pathlib import Path

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
    / "data/processed/walk_forward_validation"
)

DEVELOPMENT_END = pd.Timestamp("2026-07-01", tz="UTC")

MIN_TRAIN_HOURS = 365 * 24
VALIDATION_HOURS = 30 * 24

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

    # Confirm hourly continuity.
    timestamps = df["hour_start_utc"]

    assert timestamps.is_unique, "Duplicate timestamps found."

    assert timestamps.diff().dropna().eq(
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
    print("\nINNEVA.E — Walk-Forward Demand Validation")

    df = pd.read_csv(INPUT_FILE)
    df = build_features(df)

    # Reserve July–September 2026 as final holdout.
    development = df[
        df["hour_start_utc"] < DEVELOPMENT_END
    ].copy()

    development = development.dropna(
        subset=FEATURES + [TARGET]
    ).reset_index(drop=True)

    results = []
    predictions = []

    train_end = MIN_TRAIN_HOURS
    fold = 1

    while train_end + VALIDATION_HOURS <= len(development):
        train = development.iloc[:train_end]
        validation = development.iloc[
            train_end:train_end + VALIDATION_HOURS
        ]

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
            validation[FEATURES].astype(float)
        )

        persistence_predictions = (
            validation["demand_lag_1h"].to_numpy()
        )

        ml_metrics = calculate_metrics(
            validation[TARGET],
            ml_predictions
        )

        baseline_metrics = calculate_metrics(
            validation[TARGET],
            persistence_predictions
        )

        improvement = (
            (baseline_metrics["mae_mw"] - ml_metrics["mae_mw"])
            / baseline_metrics["mae_mw"]
        ) * 100

        results.append({
            "fold": fold,
            "train_end_utc": str(
                train["hour_start_utc"].iloc[-1]
            ),
            "validation_start_utc": str(
                validation["hour_start_utc"].iloc[0]
            ),
            "validation_end_utc": str(
                validation["hour_start_utc"].iloc[-1]
            ),
            "training_records": len(train),
            "validation_records": len(validation),
            "ml_mae_mw": ml_metrics["mae_mw"],
            "ml_rmse_mw": ml_metrics["rmse_mw"],
            "ml_mape_pct": ml_metrics["mape_pct"],
            "persistence_mae_mw": baseline_metrics["mae_mw"],
            "persistence_rmse_mw": baseline_metrics["rmse_mw"],
            "persistence_mape_pct": baseline_metrics["mape_pct"],
            "mae_improvement_pct": improvement,
        })

        fold_predictions = pd.DataFrame({
            "fold": fold,
            "hour_start_utc": validation["hour_start_utc"],
            "actual_load_mw": validation[TARGET],
            "ml_prediction_mw": ml_predictions,
            "persistence_prediction_mw": persistence_predictions,
        })

        predictions.append(fold_predictions)

        print(
            f"Fold {fold:02d} | "
            f"ML MAE: {ml_metrics['mae_mw']:.2f} MW | "
            f"Persistence MAE: "
            f"{baseline_metrics['mae_mw']:.2f} MW | "
            f"Improvement: {improvement:.2f}%"
        )

        train_end += VALIDATION_HOURS
        fold += 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results_df = pd.DataFrame(results)

    results_df.to_csv(
        OUTPUT_DIR / "walk_forward_metrics.csv",
        index=False
    )

    if predictions:
        pd.concat(
            predictions,
            ignore_index=True
        ).to_csv(
            OUTPUT_DIR / "walk_forward_predictions.csv",
            index=False
        )

    print("\nWalk-forward validation completed.")

    print(f"Total folds: {len(results_df)}")

    if not results_df.empty:
        print(
            f"Average ML MAE: "
            f"{results_df['ml_mae_mw'].mean():.2f} MW"
        )

        print(
            f"Average persistence MAE: "
            f"{results_df['persistence_mae_mw'].mean():.2f} MW"
        )

        print(
            f"Average MAE improvement: "
            f"{results_df['mae_improvement_pct'].mean():.2f}%"
        )

    print(f"\nResults saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
