
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data/development/demand_features_90d.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/baseline_forecasting"
)


def calculate_metrics(actual, predicted):
    error = actual - predicted

    mae = np.mean(np.abs(error))
    rmse = np.sqrt(np.mean(error ** 2))

    nonzero = actual != 0
    mape = (
        np.mean(np.abs(error[nonzero] / actual[nonzero])) * 100
        if nonzero.any()
        else np.nan
    )

    return {
        "mae_mw": mae,
        "rmse_mw": rmse,
        "mape_pct": mape,
    }


def main():
    print("\nINNEVA.E — Baseline Forecast Evaluation")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["hour_start_utc"]
    )

    df = df.sort_values("hour_start_utc").reset_index(drop=True)

    # Use a common evaluation window for all models.
    # First 168 hours have insufficient weekly lag history.
    evaluation = df.dropna(
        subset=[
            "actual_load_mw",
            "demand_lag_1h",
            "demand_lag_24h",
            "demand_lag_168h",
        ]
    ).copy()

    models = {
        "Persistence (1h)": "demand_lag_1h",
        "Seasonal naive (24h)": "demand_lag_24h",
        "Seasonal naive (168h)": "demand_lag_168h",
    }

    results = []

    for model_name, prediction_column in models.items():
        metrics = calculate_metrics(
            evaluation["actual_load_mw"].to_numpy(),
            evaluation[prediction_column].to_numpy()
        )

        results.append({
            "model": model_name,
            **metrics
        })

    metrics_df = pd.DataFrame(results)
    metrics_df = metrics_df.sort_values("mae_mw")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    metrics_df.to_csv(
        OUTPUT_DIR / "baseline_metrics.csv",
        index=False
    )

    prediction_columns = [
        "hour_start_utc",
        "actual_load_mw",
        "demand_lag_1h",
        "demand_lag_24h",
        "demand_lag_168h",
    ]

    evaluation[prediction_columns].to_csv(
        OUTPUT_DIR / "baseline_predictions.csv",
        index=False
    )

    print(f"\nEvaluation records: {len(evaluation):,}")
    print("\nModel comparison:")
    print(metrics_df.to_string(index=False))

    print(f"\nResults saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
