
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ============================================================
# INNEVA.E - ELECTRICITY DEMAND PATTERNS
# MODULE 12 | CHECKPOINT 12.2
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "data" / "processed" / "demand_analysis"
)

EXPECTED_HOURS = 720


def load_data():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    query = """
        SELECT
            interval_start_utc,
            electricity_demand_mw,
            demand_forecast_mw
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

    if len(df) != EXPECTED_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_HOURS} observations, "
            f"found {len(df)}"
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps detected.")

    expected = pd.date_range(
        start="2026-09-01",
        periods=EXPECTED_HOURS,
        freq="h",
        tz="UTC"
    )

    if not df["interval_start_utc"].reset_index(
        drop=True
    ).equals(pd.Series(expected)):
        raise ValueError(
            "Hourly timestamps are missing or out of order."
        )

    required = [
        "electricity_demand_mw",
        "demand_forecast_mw"
    ]

    if df[required].isna().any().any():
        raise ValueError(
            "Missing demand or forecast values."
        )

    if not np.isfinite(
        df[required].to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Non-finite demand or forecast values."
        )

    if (df[required] < 0).any().any():
        raise ValueError(
            "Negative demand or forecast values."
        )

    df["hour_utc"] = (
        df["interval_start_utc"].dt.hour
    )

    df["day_of_week"] = (
        df["interval_start_utc"].dt.dayofweek
    )

    df["day_name"] = (
        df["interval_start_utc"].dt.day_name()
    )

    df["is_weekend"] = (
        df["day_of_week"] >= 5
    )

    df["forecast_error_mw"] = (
        df["electricity_demand_mw"]
        - df["demand_forecast_mw"]
    )

    df["absolute_error_mw"] = (
        df["forecast_error_mw"].abs()
    )

    return df


def calculate_statistics(df):

    demand = df["electricity_demand_mw"]
    forecast = df["demand_forecast_mw"]

    peak_index = demand.idxmax()
    minimum_index = demand.idxmin()

    errors = demand - forecast

    mae = np.mean(np.abs(errors))

    rmse = np.sqrt(
        np.mean(np.square(errors))
    )

    # MAPE requires positive actual values.
    if (demand <= 0).any():
        mape = float("nan")
    else:
        mape = np.mean(
            np.abs(errors / demand)
        ) * 100

    weekday_mean = df.loc[
        ~df["is_weekend"],
        "electricity_demand_mw"
    ].mean()

    weekend_mean = df.loc[
        df["is_weekend"],
        "electricity_demand_mw"
    ].mean()

    hourly_profile = df.groupby(
        "hour_utc"
    )["electricity_demand_mw"].mean()

    statistics = {
        "average_demand_mw": demand.mean(),
        "peak_demand_mw": demand.max(),
        "peak_timestamp_utc": str(
            df.loc[peak_index, "interval_start_utc"]
        ),
        "minimum_demand_mw": demand.min(),
        "minimum_timestamp_utc": str(
            df.loc[minimum_index, "interval_start_utc"]
        ),
        "weekday_average_mw": weekday_mean,
        "weekend_average_mw": weekend_mean,
        "weekday_minus_weekend_mw": (
            weekday_mean - weekend_mean
        ),
        "highest_average_demand_hour_utc": int(
            hourly_profile.idxmax()
        ),
        "lowest_average_demand_hour_utc": int(
            hourly_profile.idxmin()
        ),
        "forecast_mae_mw": mae,
        "forecast_rmse_mw": rmse,
        "forecast_mape_pct": mape,
        "forecast_bias_mw": errors.mean(),
    }

    return statistics


def create_hourly_demand_chart(df):

    fig, ax = plt.subplots(figsize=(13, 5))

    ax.plot(
        df["interval_start_utc"],
        df["electricity_demand_mw"],
        linewidth=1,
        label="Actual demand"
    )

    ax.set_title(
        "Electricity Demand - September 2026"
    )
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Electricity demand (MW)")
    ax.grid(alpha=0.3)
    ax.legend()

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "01_hourly_demand.png",
        dpi=160
    )

    plt.close(fig)


def create_daily_profile_chart(df):

    profile = df.groupby(
        "hour_utc"
    )["electricity_demand_mw"].mean()

    fig, ax = plt.subplots(figsize=(11, 5))

    ax.plot(
        profile.index,
        profile.values,
        marker="o"
    )

    ax.set_title(
        "Average Electricity Demand by Hour"
    )
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Average demand (MW)")
    ax.set_xticks(range(0, 24))
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "02_daily_demand_profile.png",
        dpi=160
    )

    plt.close(fig)


def create_weekday_weekend_chart(df):

    profiles = df.groupby(
        ["is_weekend", "hour_utc"]
    )["electricity_demand_mw"].mean().unstack(0)

    fig, ax = plt.subplots(figsize=(11, 5))

    ax.plot(
        profiles.index,
        profiles[False],
        marker="o",
        label="Weekday"
    )

    ax.plot(
        profiles.index,
        profiles[True],
        marker="o",
        label="Weekend"
    )

    ax.set_title(
        "Weekday vs Weekend Demand Profile"
    )
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Average demand (MW)")
    ax.set_xticks(range(0, 24))
    ax.legend()
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "03_weekday_weekend.png",
        dpi=160
    )

    plt.close(fig)


def create_forecast_comparison_chart(df):

    fig, ax = plt.subplots(figsize=(13, 5))

    ax.plot(
        df["interval_start_utc"],
        df["electricity_demand_mw"],
        linewidth=1,
        label="Actual demand"
    )

    ax.plot(
        df["interval_start_utc"],
        df["demand_forecast_mw"],
        linewidth=1,
        alpha=0.75,
        label="Day-ahead forecast"
    )

    ax.set_title(
        "Actual vs Forecast Electricity Demand"
    )
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Demand (MW)")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "04_forecast_comparison.png",
        dpi=160
    )

    plt.close(fig)


def save_reports(df, statistics):

    summary = pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in statistics.items()
        ]
    )

    summary.to_csv(
        OUTPUT_DIRECTORY / "demand_statistics.csv",
        index=False
    )

    df.to_csv(
        OUTPUT_DIRECTORY / "hourly_demand_analysis.csv",
        index=False
    )


def print_statistics(stats):

    print("\n" + "=" * 65)
    print("ELECTRICITY DEMAND ANALYSIS")
    print("=" * 65)

    print("\nDEMAND STATISTICS")
    print("-" * 65)

    print(
        f"Average demand: "
        f"{stats['average_demand_mw']:,.2f} MW"
    )

    print(
        f"Peak demand: "
        f"{stats['peak_demand_mw']:,.2f} MW"
    )

    print(
        f"Peak timestamp: "
        f"{stats['peak_timestamp_utc']}"
    )

    print(
        f"Minimum demand: "
        f"{stats['minimum_demand_mw']:,.2f} MW"
    )

    print(
        f"Minimum timestamp: "
        f"{stats['minimum_timestamp_utc']}"
    )

    print("\nDEMAND PATTERNS")
    print("-" * 65)

    print(
        f"Weekday average: "
        f"{stats['weekday_average_mw']:,.2f} MW"
    )

    print(
        f"Weekend average: "
        f"{stats['weekend_average_mw']:,.2f} MW"
    )

    print(
        f"Weekday minus weekend: "
        f"{stats['weekday_minus_weekend_mw']:,.2f} MW"
    )

    print(
        f"Highest average demand hour (UTC): "
        f"{stats['highest_average_demand_hour_utc']:02d}:00"
    )

    print(
        f"Lowest average demand hour (UTC): "
        f"{stats['lowest_average_demand_hour_utc']:02d}:00"
    )

    print("\nFORECAST ACCURACY")
    print("-" * 65)

    print(
        f"MAE: {stats['forecast_mae_mw']:,.2f} MW"
    )

    print(
        f"RMSE: {stats['forecast_rmse_mw']:,.2f} MW"
    )

    print(
        f"MAPE: {stats['forecast_mape_pct']:.2f}%"
    )

    print(
        f"Forecast bias (actual - forecast): "
        f"{stats['forecast_bias_mw']:,.2f} MW"
    )


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - DEMAND PATTERN ANALYTICS")
    print("=" * 65)

    df = load_data()

    print(f"Data loaded: {len(df)} hourly observations")

    statistics = calculate_statistics(df)

    print_statistics(statistics)

    create_hourly_demand_chart(df)
    create_daily_profile_chart(df)
    create_weekday_weekend_chart(df)
    create_forecast_comparison_chart(df)

    save_reports(df, statistics)

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 12.2 completed successfully!")


if __name__ == "__main__":
    main()
