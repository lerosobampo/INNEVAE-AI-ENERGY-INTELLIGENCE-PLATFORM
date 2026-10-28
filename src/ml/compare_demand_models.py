
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ============================================================
# INNEVA.E - DEMAND FORECAST MODEL COMPARISON
# MODULE 13 | CHECKPOINT 13.2
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml_model_comparison"
)

EXPECTED_HOURS = 720

# Keep the original 140-hour test window from Checkpoint 13.1.
TEST_START_UTC = pd.Timestamp(
    "2026-09-25 04:00:00",
    tz="UTC"
)

FEATURE_COLUMNS = [
    "demand_lag_1",
    "demand_lag_2",
    "demand_lag_24",
    "demand_lag_48",
    "hour_sin",
    "hour_cos",
    "day_of_week",
    "is_weekend",
]

TARGET_COLUMN = "electricity_demand_mw"


def load_data():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    query = """
        SELECT
            interval_start_utc,
            electricity_demand_mw
        FROM integrated_energy_intelligence
        ORDER BY interval_start_utc
    """

    with sqlite3.connect(DATABASE_PATH) as connection:
        df = pd.read_sql_query(query, connection)

    df["interval_start_utc"] = pd.to_datetime(
        df["interval_start_utc"],
        utc=True,
        errors="raise"
    )

    df[TARGET_COLUMN] = pd.to_numeric(
        df[TARGET_COLUMN],
        errors="coerce"
    )

    return df


def validate_data(df):

    if len(df) != EXPECTED_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_HOURS} hourly records, "
            f"found {len(df)}."
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps detected.")

    expected = pd.date_range(
        "2026-09-01",
        periods=EXPECTED_HOURS,
        freq="h",
        tz="UTC"
    )

    actual = df[
        "interval_start_utc"
    ].reset_index(drop=True)

    if not actual.equals(pd.Series(expected)):
        raise ValueError(
            "Hourly timestamp coverage is incomplete."
        )

    if df[TARGET_COLUMN].isna().any():
        raise ValueError(
            "Missing electricity demand values."
        )

    if not np.isfinite(
        df[TARGET_COLUMN].to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Non-finite electricity demand detected."
        )

    if (df[TARGET_COLUMN] < 0).any():
        raise ValueError(
            "Negative electricity demand detected."
        )

    print(f"Validated hourly records: {len(df)}")


def engineer_features(df):

    df = df.copy()

    for lag in [1, 2, 24, 48]:
        df[f"demand_lag_{lag}"] = (
            df[TARGET_COLUMN].shift(lag)
        )

    hour = df["interval_start_utc"].dt.hour

    df["hour_sin"] = np.sin(
        2 * np.pi * hour / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * hour / 24
    )

    df["day_of_week"] = (
        df["interval_start_utc"].dt.day_of_week
    )

    df["is_weekend"] = (
        df["day_of_week"] >= 5
    ).astype(int)

    df = df.dropna(
        subset=FEATURE_COLUMNS + [TARGET_COLUMN]
    ).reset_index(drop=True)

    return df


def split_data(df):

    train = df.loc[
        df["interval_start_utc"] < TEST_START_UTC
    ].copy()

    test = df.loc[
        df["interval_start_utc"] >= TEST_START_UTC
    ].copy()

    if train.empty or test.empty:
        raise ValueError(
            "Training or testing data is empty."
        )

    if len(test) != 140:
        raise ValueError(
            f"Expected 140 test hours, found {len(test)}."
        )

    if (
        train["interval_start_utc"].max()
        >= test["interval_start_utc"].min()
    ):
        raise ValueError(
            "Chronological train/test split failed."
        )

    print("\nDATA SPLIT")
    print("-" * 65)

    print(f"Training observations: {len(train)}")
    print(f"Testing observations: {len(test)}")

    print(
        f"Training ends: "
        f"{train['interval_start_utc'].max()}"
    )

    print(
        f"Testing starts: "
        f"{test['interval_start_utc'].min()}"
    )

    return train, test


def evaluate(actual, predicted):

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    mae = mean_absolute_error(actual, predicted)

    rmse = np.sqrt(
        mean_squared_error(actual, predicted)
    )

    valid = actual != 0

    mape = (
        np.mean(
            np.abs(
                (actual[valid] - predicted[valid])
                / actual[valid]
            )
        ) * 100
        if valid.any()
        else float("nan")
    )

    bias = np.mean(actual - predicted)

    return {
        "MAE_MW": mae,
        "RMSE_MW": rmse,
        "MAPE_pct": mape,
        "Bias_MW": bias,
    }


def build_models():

    return {
        "Linear Regression": Pipeline([
            ("scaler", StandardScaler()),
            ("model", LinearRegression()),
        ]),

        "Ridge Regression": Pipeline([
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]),

        "Random Forest": RandomForestRegressor(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=4,
            random_state=42,
            n_jobs=-1
        ),
    }


def compare_models(train, test):

    X_train = train[FEATURE_COLUMNS]
    y_train = train[TARGET_COLUMN]

    X_test = test[FEATURE_COLUMNS]
    y_test = test[TARGET_COLUMN]

    predictions = test[
        ["interval_start_utc", TARGET_COLUMN]
    ].copy()

    model_predictions = {
        "Previous Hour": test[
            "demand_lag_1"
        ].to_numpy(),

        "Previous Day": test[
            "demand_lag_24"
        ].to_numpy(),
    }

    trained_models = {}

    for name, model in build_models().items():

        model.fit(X_train, y_train)

        model_predictions[name] = (
            model.predict(X_test)
        )

        trained_models[name] = model

    results = []

    for name, predicted in model_predictions.items():

        metrics = evaluate(
            y_test,
            predicted
        )

        results.append({
            "model": name,
            **metrics
        })

        column_name = (
            name.lower()
            .replace(" ", "_")
            + "_prediction_mw"
        )

        predictions[column_name] = predicted

    results_df = pd.DataFrame(results)

    results_df = results_df.sort_values(
        "MAE_MW"
    ).reset_index(drop=True)

    return (
        results_df,
        predictions,
        trained_models
    )


def create_comparison_chart(results):

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.barh(
        results["model"],
        results["MAE_MW"]
    )

    ax.invert_yaxis()

    ax.set_title(
        "Electricity Demand Forecast Model Comparison"
    )

    ax.set_xlabel("Mean Absolute Error (MW)")
    ax.grid(axis="x", alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "01_model_comparison.png",
        dpi=160
    )

    plt.close(fig)


def create_forecast_chart(predictions, results):

    best_model = results.iloc[0]["model"]

    best_column = (
        best_model.lower()
        .replace(" ", "_")
        + "_prediction_mw"
    )

    fig, ax = plt.subplots(figsize=(13, 6))

    ax.plot(
        predictions["interval_start_utc"],
        predictions[TARGET_COLUMN],
        label="Actual demand",
        linewidth=1.8
    )

    ax.plot(
        predictions["interval_start_utc"],
        predictions[
            "previous_hour_prediction_mw"
        ],
        label="Previous-hour baseline",
        alpha=0.65
    )

    if best_column != "previous_hour_prediction_mw":

        ax.plot(
            predictions["interval_start_utc"],
            predictions[best_column],
            label=f"Best model: {best_model}",
            linewidth=1.2
        )

    ax.set_title(
        "Electricity Demand: Actual vs Predictions"
    )

    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Demand (MW)")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "02_best_model_forecast.png",
        dpi=160
    )

    plt.close(fig)


def create_feature_importance_chart(trained_models):

    forest = trained_models["Random Forest"]

    importances = pd.DataFrame({
        "feature": FEATURE_COLUMNS,
        "importance": forest.feature_importances_,
    }).sort_values("importance")

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.barh(
        importances["feature"],
        importances["importance"]
    )

    ax.set_title(
        "Random Forest Feature Importance"
    )

    ax.set_xlabel("Relative importance")
    ax.grid(axis="x", alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "03_feature_importance.png",
        dpi=160
    )

    plt.close(fig)

    return importances


def save_results(
    results,
    predictions,
    importances
):

    results.to_csv(
        OUTPUT_DIRECTORY / "model_comparison.csv",
        index=False
    )

    predictions.to_csv(
        OUTPUT_DIRECTORY / "model_predictions.csv",
        index=False
    )

    importances.to_csv(
        OUTPUT_DIRECTORY / "feature_importance.csv",
        index=False
    )


def print_results(results):

    print("\n" + "=" * 65)
    print("MODEL PERFORMANCE COMPARISON")
    print("=" * 65)

    print(
        results.to_string(
            index=False,
            float_format=lambda value: f"{value:,.2f}"
        )
    )

    best = results.iloc[0]

    print("\nBEST MODEL")
    print("-" * 65)

    print(f"Model: {best['model']}")
    print(f"MAE: {best['MAE_MW']:,.2f} MW")
    print(f"RMSE: {best['RMSE_MW']:,.2f} MW")
    print(f"MAPE: {best['MAPE_pct']:.2f}%")
    print(f"Bias: {best['Bias_MW']:,.2f} MW")


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - FORECAST MODEL COMPARISON")
    print("=" * 65)

    df = load_data()

    validate_data(df)

    features_df = engineer_features(df)

    print(
        f"Observations after feature engineering: "
        f"{len(features_df)}"
    )

    train, test = split_data(features_df)

    (
        results,
        predictions,
        trained_models
    ) = compare_models(train, test)

    print_results(results)

    create_comparison_chart(results)
    create_forecast_chart(predictions, results)

    importances = create_feature_importance_chart(
        trained_models
    )

    save_results(
        results,
        predictions,
        importances
    )

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 13.2 completed successfully!")


if __name__ == "__main__":
    main()
