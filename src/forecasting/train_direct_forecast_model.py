
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_FILE = (
    PROJECT_ROOT
    / "data/processed/direct_forecasting/direct_training_data.csv"
)

MODEL_FILE = (
    PROJECT_ROOT
    / "models/direct_demand_model.joblib"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/direct_forecasting/validation"
)

VALIDATION_START = pd.Timestamp(
    "2026-03-01T00:00:00+00:00"
)

VALIDATION_END = pd.Timestamp(
    "2026-06-01T00:00:00+00:00"
)

FEATURES = [
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

TARGET = "actual_load_mw"

HORIZONS = {
    "24h": 24,
    "7d": 168,
    "30d": 720,
}


def load_dataset():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Training dataset not found: {DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE)

    required = (
        FEATURES
        + [
            TARGET,
            "issue_time_utc",
            "target_time_utc",
        ]
    )

    missing = set(required) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    for column in [
        "issue_time_utc",
        "target_time_utc",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            utc=True,
        )

    numeric = df[FEATURES + [TARGET]].apply(
        pd.to_numeric,
        errors="raise",
    )

    if not np.isfinite(
        numeric.to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Dataset contains non-finite numeric values."
        )

    df[FEATURES + [TARGET]] = numeric

    if df.duplicated(
        ["issue_time_utc", "lead_hours"]
    ).any():
        raise ValueError(
            "Duplicate forecast examples found."
        )

    expected_targets = (
        df["issue_time_utc"]
        + pd.to_timedelta(
            df["lead_hours"] - 1,
            unit="h",
        )
    )

    if not (
        df["target_time_utc"] == expected_targets
    ).all():
        raise ValueError(
            "Forecast lead times do not match targets."
        )

    return df


def calculate_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) == 0:
        raise ValueError(
            "Cannot evaluate an empty dataset."
        )

    errors = actual - predicted

    mae = np.mean(np.abs(errors))
    rmse = np.sqrt(np.mean(errors ** 2))

    nonzero = actual != 0

    mape = (
        np.mean(
            np.abs(
                errors[nonzero] / actual[nonzero]
            )
        ) * 100
        if nonzero.any()
        else np.nan
    )

    return {
        "mae_mw": float(mae),
        "rmse_mw": float(rmse),
        "mape_pct": float(mape),
    }


def main():
    print(
        "\nINNEVA.E — Direct Forecast Model Training"
    )
    print("-----------------------------------------")

    df = load_dataset()

    # Training targets must finish before
    # the validation period begins.
    train = df[
        (df["issue_time_utc"] < VALIDATION_START)
        & (df["target_time_utc"] < VALIDATION_START)
    ].copy()

    # Validation origins begin in March.
    # Their target observations remain outside
    # the training target period.
    validation = df[
        (df["issue_time_utc"] >= VALIDATION_START)
        & (df["issue_time_utc"] < VALIDATION_END)
    ].copy()

    if train.empty or validation.empty:
        raise ValueError(
            "Training or validation dataset is empty."
        )

    if train["target_time_utc"].max() >= (
        validation["issue_time_utc"].min()
    ):
        raise AssertionError(
            "Training targets overlap validation origins."
        )

    train_origins = set(train["issue_time_utc"])
    validation_origins = set(
        validation["issue_time_utc"]
    )

    if train_origins.intersection(
        validation_origins
    ):
        raise AssertionError(
            "Training and validation origins overlap."
        )

    print("\nDATA SPLIT")
    print(f"Training examples: {len(train):,}")
    print(
        f"Training origins: "
        f"{train['issue_time_utc'].nunique()}"
    )
    print(
        f"Last training target: "
        f"{train['target_time_utc'].max()}"
    )

    print(
        f"\nValidation examples: "
        f"{len(validation):,}"
    )
    print(
        f"Validation origins: "
        f"{validation['issue_time_utc'].nunique()}"
    )
    print(
        f"First validation origin: "
        f"{validation['issue_time_utc'].min()}"
    )
    print(
        f"Last validation origin: "
        f"{validation['issue_time_utc'].max()}"
    )

    print("\nTRAINING MODEL")

    model = HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=42,
    )

    model.fit(
        train[FEATURES],
        train[TARGET],
    )

    validation = validation.copy()

    validation["direct_ml_mw"] = model.predict(
        validation[FEATURES]
    )

    if not np.isfinite(
        validation["direct_ml_mw"]
    ).all():
        raise ValueError(
            "Model produced invalid predictions."
        )

    methods = {
        "Direct ML": "direct_ml_mw",
        "Seasonal Naive 24h": "seasonal_daily_mw",
        "Seasonal Naive 168h": "seasonal_weekly_mw",
    }

    metric_rows = []
    issue_rows = []

    for horizon, hours in HORIZONS.items():
        subset = validation[
            validation["lead_hours"] <= hours
        ].copy()

        print(f"\n{horizon.upper()} VALIDATION")
        print(
            f"Forecast origins: "
            f"{subset['issue_time_utc'].nunique()}"
        )
        print(f"Evaluated hours: {len(subset):,}")

        for name, column in methods.items():
            metrics = calculate_metrics(
                subset[TARGET],
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
            for name, column in methods.items():
                metrics = calculate_metrics(
                    group[TARGET],
                    group[column],
                )

                issue_rows.append({
                    "horizon": horizon,
                    "issue_time_utc": issue_time,
                    "model": name,
                    **metrics,
                })

    metrics_df = pd.DataFrame(metric_rows)
    issue_df = pd.DataFrame(issue_rows)

    print("\nOVERALL VALIDATION METRICS")

    for horizon in HORIZONS:
        print(f"\n{horizon.upper()}")

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

        direct_mae = subset.loc[
            subset["model"] == "Direct ML",
            "mae_mw",
        ].iloc[0]

        weekly_mae = subset.loc[
            subset["model"] == "Seasonal Naive 168h",
            "mae_mw",
        ].iloc[0]

        improvement = (
            (weekly_mae - direct_mae)
            / weekly_mae * 100
        )

        print(
            f"Direct ML improvement vs weekly naive: "
            f"{improvement:.2f}%"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    MODEL_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact = {
        "model": model,
        "features": FEATURES,
        "target": TARGET,
        "model_type": "direct_multi_horizon",
        "maximum_horizon_hours": 720,
        "training_target_end_utc": str(
            train["target_time_utc"].max()
        ),
        "validation_start_utc": str(
            VALIDATION_START
        ),
    }

    joblib.dump(
        artifact,
        MODEL_FILE,
    )

    validation.to_csv(
        OUTPUT_DIR / "validation_predictions.csv",
        index=False,
    )

    metrics_df.to_csv(
        OUTPUT_DIR / "validation_metrics.csv",
        index=False,
    )

    issue_df.to_csv(
        OUTPUT_DIR / "validation_metrics_by_issue.csv",
        index=False,
    )

    print("\nOUTPUT FILES")
    print(MODEL_FILE)
    print(
        OUTPUT_DIR / "validation_predictions.csv"
    )
    print(
        OUTPUT_DIR / "validation_metrics.csv"
    )
    print(
        OUTPUT_DIR / "validation_metrics_by_issue.csv"
    )

    print(
        "\nDIRECT FORECAST MODEL TRAINING COMPLETED"
    )


if __name__ == "__main__":
    main()
