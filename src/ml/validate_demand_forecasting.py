
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from demand_forecasting_tool import forecast_next_hour


# ============================================================
# INNEVA.E - FORECAST DIAGNOSTICS AND VALIDATION
# MODULE 13 | CHECKPOINT 13.3
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "forecast_validation"
)

TEST_START_UTC = pd.Timestamp(
    "2026-09-25 04:00:00",
    tz="UTC"
)

VALIDATION_WINDOWS = [
    (
        "Window 1",
        "2026-09-11 00:00:00",
        "2026-09-16 00:00:00",
    ),
    (
        "Window 2",
        "2026-09-16 00:00:00",
        "2026-09-21 00:00:00",
    ),
    (
        "Window 3",
        "2026-09-21 00:00:00",
        "2026-09-26 00:00:00",
    ),
]


def load_data():

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

    df["electricity_demand_mw"] = pd.to_numeric(
        df["electricity_demand_mw"],
        errors="coerce"
    )

    if len(df) != 720:
        raise ValueError(
            f"Expected 720 hourly records; found {len(df)}."
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps detected.")

    expected = pd.date_range(
        "2026-09-01",
        periods=720,
        freq="h",
        tz="UTC"
    )

    if not df["interval_start_utc"].reset_index(
        drop=True
    ).equals(pd.Series(expected)):
        raise ValueError(
            "Hourly timestamps are not complete."
        )

    if df["electricity_demand_mw"].isna().any():
        raise ValueError(
            "Missing demand observations."
        )

    values = df[
        "electricity_demand_mw"
    ].to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise ValueError(
            "Non-finite demand observations."
        )

    if (values < 0).any():
        raise ValueError(
            "Negative demand observations."
        )

    df["previous_hour_mw"] = (
        df["electricity_demand_mw"].shift(1)
    )

    df["previous_day_mw"] = (
        df["electricity_demand_mw"].shift(24)
    )

    return df


def calculate_metrics(actual, predicted):

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    errors = actual - predicted

    mae = np.mean(np.abs(errors))

    rmse = np.sqrt(np.mean(errors ** 2))

    nonzero = actual != 0

    mape = (
        np.mean(
            np.abs(errors[nonzero] / actual[nonzero])
        ) * 100
        if nonzero.any()
        else float("nan")
    )

    bias = np.mean(errors)

    return {
        "MAE_MW": mae,
        "RMSE_MW": rmse,
        "MAPE_pct": mape,
        "Bias_MW": bias,
    }


def analyze_distribution_shift(df):

    train = df.loc[
        df["interval_start_utc"] < TEST_START_UTC
    ]

    test = df.loc[
        df["interval_start_utc"] >= TEST_START_UTC
    ]

    train_mean = train[
        "electricity_demand_mw"
    ].mean()

    test_mean = test[
        "electricity_demand_mw"
    ].mean()

    print("\nDEMAND DISTRIBUTION")
    print("-" * 65)

    print(f"Training mean: {train_mean:,.2f} MW")
    print(f"Testing mean: {test_mean:,.2f} MW")

    print(
        f"Mean difference (test - train): "
        f"{test_mean - train_mean:,.2f} MW"
    )

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.hist(
        train["electricity_demand_mw"],
        bins=25,
        alpha=0.6,
        label="Training period"
    )

    ax.hist(
        test["electricity_demand_mw"],
        bins=25,
        alpha=0.6,
        label="Testing period"
    )

    ax.set_title(
        "Electricity Demand Distribution: Train vs Test"
    )

    ax.set_xlabel("Electricity demand (MW)")
    ax.set_ylabel("Number of observations")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "01_demand_distribution.png",
        dpi=160
    )

    plt.close(fig)

    summary = pd.DataFrame([
        {
            "period": "train",
            "observations": len(train),
            "mean_mw": train_mean,
            "std_mw": train[
                "electricity_demand_mw"
            ].std(),
        },
        {
            "period": "test",
            "observations": len(test),
            "mean_mw": test_mean,
            "std_mw": test[
                "electricity_demand_mw"
            ].std(),
        },
    ])

    summary.to_csv(
        OUTPUT_DIRECTORY / "distribution_summary.csv",
        index=False
    )


def evaluate_windows(df):

    results = []

    print("\nWALK-FORWARD VALIDATION")
    print("-" * 65)

    for window_name, start, end in VALIDATION_WINDOWS:

        start = pd.Timestamp(start, tz="UTC")
        end = pd.Timestamp(end, tz="UTC")

        window = df.loc[
            (df["interval_start_utc"] >= start)
            & (df["interval_start_utc"] < end)
        ].copy()

        if len(window) != 120:
            raise ValueError(
                f"{window_name}: expected 120 hours, "
                f"found {len(window)}."
            )

        for model_name, column in [
            ("Previous Hour", "previous_hour_mw"),
            ("Previous Day", "previous_day_mw"),
        ]:

            if window[column].isna().any():
                raise ValueError(
                    f"{window_name}: missing lag values."
                )

            metrics = calculate_metrics(
                window["electricity_demand_mw"],
                window[column]
            )

            results.append({
                "window": window_name,
                "model": model_name,
                **metrics
            })

    results_df = pd.DataFrame(results)

    print(
        results_df.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}"
        )
    )

    results_df.to_csv(
        OUTPUT_DIRECTORY / "walk_forward_metrics.csv",
        index=False
    )

    return results_df


def create_window_comparison(results):

    pivot = results.pivot(
        index="window",
        columns="model",
        values="MAE_MW"
    )

    ax = pivot.plot(
        kind="bar",
        figsize=(11, 6)
    )

    ax.set_title(
        "Forecast Accuracy Across Evaluation Windows"
    )

    ax.set_xlabel("Validation window")
    ax.set_ylabel("MAE (MW)")
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.3)

    fig = ax.get_figure()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "02_window_comparison.png",
        dpi=160
    )

    plt.close(fig)


def analyze_final_test_errors(df):

    test = df.loc[
        df["interval_start_utc"] >= TEST_START_UTC
    ].copy()

    test["forecast_error_mw"] = (
        test["electricity_demand_mw"]
        - test["previous_hour_mw"]
    )

    test["absolute_error_mw"] = (
        test["forecast_error_mw"].abs()
    )

    print("\nFINAL TEST PERIOD")
    print("-" * 65)

    metrics = calculate_metrics(
        test["electricity_demand_mw"],
        test["previous_hour_mw"]
    )

    for name, value in metrics.items():
        print(f"{name}: {value:,.2f}")

    print("\nLARGEST FORECAST ERRORS")

    print(
        test.nlargest(
            5,
            "absolute_error_mw"
        )[
            [
                "interval_start_utc",
                "electricity_demand_mw",
                "previous_hour_mw",
                "forecast_error_mw",
            ]
        ].to_string(index=False)
    )

    test.to_csv(
        OUTPUT_DIRECTORY / "final_test_errors.csv",
        index=False
    )


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - FORECAST VALIDATION")
    print("=" * 65)

    df = load_data()

    print(f"Validated hourly records: {len(df)}")

    analyze_distribution_shift(df)

    results = evaluate_windows(df)

    create_window_comparison(results)

    analyze_final_test_errors(df)

    print("\nREUSABLE FORECAST TOOL")
    print("-" * 65)

    forecast = forecast_next_hour()

    print(
        f"Forecast timestamp: "
        f"{forecast['forecast_timestamp_utc']}"
    )

    print(
        f"Predicted demand: "
        f"{forecast['predicted_demand_mw']:,.2f} MW"
    )

    print(
        f"Model: {forecast['model']}"
    )

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 13.3 completed successfully!")


if __name__ == "__main__":
    main()
