
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error
)

# ============================================================
# INNEVA.E - FIRST ELECTRICITY DEMAND FORECAST
# MODULE 13 | CHECKPOINT 13.1
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "data" / "processed" / "ml_forecasting"
)

EXPECTED_HOURS = 720

FEATURE_COLUMNS = [
    "demand_lag_1",
    "demand_lag_2",
    "demand_lag_24",
    "hour_sin",
    "hour_cos",
    "day_of_week",
    "is_weekend",
]

TARGET_COLUMN = "electricity_demand_mw"


def load_data():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

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
        utc=True
    )

    df[TARGET_COLUMN] = pd.to_numeric(
        df[TARGET_COLUMN],
        errors="coerce"
    )

    return df


def validate_data(df):

    if len(df) != EXPECTED_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_HOURS} hours, "
            f"found {len(df)}"
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps detected.")

    expected = pd.date_range(
        "2026-09-01",
        periods=EXPECTED_HOURS,
        freq="h",
        tz="UTC"
    )

    actual = df["interval_start_utc"].reset_index(
        drop=True
    )

    if not actual.equals(pd.Series(expected)):
        raise ValueError(
            "Incomplete hourly timestamp coverage."
        )

    if df[TARGET_COLUMN].isna().any():
        raise ValueError("Missing electricity demand values.")

    if not np.isfinite(df[TARGET_COLUMN]).all():
        raise ValueError("Non-finite demand values detected.")

    if (df[TARGET_COLUMN] < 0).any():
        raise ValueError("Negative electricity demand detected.")

    print(f"Validated hourly records: {len(df)}")


def engineer_features(df):

    df = df.copy()

    # Lag features contain only earlier observations.
    df["demand_lag_1"] = (
        df[TARGET_COLUMN].shift(1)
    )

    df["demand_lag_2"] = (
        df[TARGET_COLUMN].shift(2)
    )

    df["demand_lag_24"] = (
        df[TARGET_COLUMN].shift(24)
    )

    # Calendar features are known in advance.
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

    # First 24 rows lack enough history.
    df = df.dropna(
        subset=FEATURE_COLUMNS + [TARGET_COLUMN]
    ).reset_index(drop=True)

    return df


def split_data(df):

    # First 80% for training; final 20% for testing.
    split_index = int(len(df) * 0.8)

    train = df.iloc[:split_index].copy()
    test = df.iloc[split_index:].copy()

    if train.empty or test.empty:
        raise ValueError("Empty training or test dataset.")

    if (
        train["interval_start_utc"].max()
        >= test["interval_start_utc"].min()
    ):
        raise ValueError("Chronological split failed.")

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


def evaluate_predictions(actual, predicted):

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    mae = mean_absolute_error(actual, predicted)

    rmse = np.sqrt(
        mean_squared_error(actual, predicted)
    )

    nonzero = actual != 0

    mape = (
        np.mean(
            np.abs(
                (actual[nonzero] - predicted[nonzero])
                / actual[nonzero]
            )
        ) * 100
        if nonzero.any()
        else float("nan")
    )

    bias = np.mean(actual - predicted)

    return {
        "MAE_MW": mae,
        "RMSE_MW": rmse,
        "MAPE_pct": mape,
        "Bias_MW": bias,
    }


def train_and_evaluate(train, test):

    X_train = train[FEATURE_COLUMNS]
    y_train = train[TARGET_COLUMN]

    X_test = test[FEATURE_COLUMNS]
    y_test = test[TARGET_COLUMN]

    # Baseline: predict the same demand as one hour ago.
    baseline_predictions = test[
        "demand_lag_1"
    ].to_numpy()

    # Machine learning model.
    model = LinearRegression()

    model.fit(X_train, y_train)

    model_predictions = model.predict(X_test)

    baseline_metrics = evaluate_predictions(
        y_test,
        baseline_predictions
    )

    model_metrics = evaluate_predictions(
        y_test,
        model_predictions
    )

    predictions = test[
        ["interval_start_utc", TARGET_COLUMN]
    ].copy()

    predictions["baseline_prediction_mw"] = (
        baseline_predictions
    )

    predictions["model_prediction_mw"] = (
        model_predictions
    )

    coefficients = pd.DataFrame({
        "feature": FEATURE_COLUMNS,
        "coefficient": model.coef_,
    })

    return (
        baseline_metrics,
        model_metrics,
        predictions,
        coefficients
    )


def print_metrics(baseline_metrics, model_metrics):

    print("\n" + "=" * 65)
    print("FORECAST PERFORMANCE")
    print("=" * 65)

    for name, metrics in [
        ("BASELINE: PREVIOUS HOUR", baseline_metrics),
        ("MACHINE LEARNING: LINEAR REGRESSION", model_metrics),
    ]:

        print(f"\n{name}")
        print("-" * 65)

        print(f"MAE: {metrics['MAE_MW']:,.2f} MW")
        print(f"RMSE: {metrics['RMSE_MW']:,.2f} MW")
        print(f"MAPE: {metrics['MAPE_pct']:.2f}%")
        print(f"Bias: {metrics['Bias_MW']:,.2f} MW")

    baseline_mae = baseline_metrics["MAE_MW"]
    model_mae = model_metrics["MAE_MW"]

    if baseline_mae > 0:
        improvement = (
            (baseline_mae - model_mae)
            / baseline_mae * 100
        )

        print("\nMODEL VS BASELINE")
        print("-" * 65)

        print(
            f"MAE improvement: {improvement:.2f}%"
        )

        if improvement > 0:
            print("Model outperformed the baseline.")
        else:
            print(
                "Model did not outperform the baseline."
            )


def create_forecast_chart(predictions):

    fig, ax = plt.subplots(figsize=(13, 6))

    ax.plot(
        predictions["interval_start_utc"],
        predictions[TARGET_COLUMN],
        label="Actual demand",
        linewidth=1.8
    )

    ax.plot(
        predictions["interval_start_utc"],
        predictions["baseline_prediction_mw"],
        label="Previous-hour baseline",
        linewidth=1,
        alpha=0.7
    )

    ax.plot(
        predictions["interval_start_utc"],
        predictions["model_prediction_mw"],
        label="Linear regression",
        linewidth=1.2
    )

    ax.set_title(
        "One-Hour-Ahead Electricity Demand Forecast"
    )

    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Electricity demand (MW)")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "01_demand_forecast.png",
        dpi=160
    )

    plt.close(fig)


def create_error_chart(predictions):

    actual = predictions[TARGET_COLUMN]

    baseline_error = (
        actual - predictions["baseline_prediction_mw"]
    )

    model_error = (
        actual - predictions["model_prediction_mw"]
    )

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.hist(
        baseline_error,
        bins=25,
        alpha=0.5,
        label="Baseline"
    )

    ax.hist(
        model_error,
        bins=25,
        alpha=0.5,
        label="Linear regression"
    )

    ax.set_title("Forecast Error Distribution")
    ax.set_xlabel("Actual minus predicted (MW)")
    ax.set_ylabel("Number of hours")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "02_forecast_errors.png",
        dpi=160
    )

    plt.close(fig)


def save_results(
    baseline_metrics,
    model_metrics,
    predictions,
    coefficients
):

    predictions.to_csv(
        OUTPUT_DIRECTORY / "demand_predictions.csv",
        index=False
    )

    coefficients.to_csv(
        OUTPUT_DIRECTORY / "model_coefficients.csv",
        index=False
    )

    metrics_rows = []

    for model_name, metrics in [
        ("previous_hour_baseline", baseline_metrics),
        ("linear_regression", model_metrics),
    ]:
        metrics_rows.append({
            "model": model_name,
            **metrics
        })

    pd.DataFrame(metrics_rows).to_csv(
        OUTPUT_DIRECTORY / "forecast_metrics.csv",
        index=False
    )


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - FIRST DEMAND FORECAST")
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
        baseline_metrics,
        model_metrics,
        predictions,
        coefficients
    ) = train_and_evaluate(train, test)

    print_metrics(
        baseline_metrics,
        model_metrics
    )

    create_forecast_chart(predictions)
    create_error_chart(predictions)

    save_results(
        baseline_metrics,
        model_metrics,
        predictions,
        coefficients
    )

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 13.1 completed successfully!")


if __name__ == "__main__":
    main()
