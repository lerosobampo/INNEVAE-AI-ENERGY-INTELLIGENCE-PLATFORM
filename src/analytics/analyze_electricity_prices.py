
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ============================================================
# INNEVA.E - ELECTRICITY PRICE ANALYSIS
# MODULE 12 | CHECKPOINT 12.5
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "electricity_price_analysis"
)

EXPECTED_HOURS = 720
EXPECTED_MISSING_PRICES = 2

PRICE_COLUMN = "wholesale_price_eur_mwh"

FEATURES = {
    "Electricity demand": "electricity_demand_mw",
    "Solar generation": "solar_generation_avg_mw",
    "Onshore wind": "wind_onshore_generation_avg_mw",
    "Offshore wind": "wind_offshore_generation_avg_mw",
    "Total renewables": "total_renewable_generation_avg_mw",
    "Wind speed": "avg_wind_speed_ms",
    "Temperature": "avg_air_temperature_c",
    "Solar radiation": "avg_solar_radiation_j_cm2",
}


def load_data():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    query = """
        SELECT
            interval_start_utc,
            electricity_demand_mw,
            solar_generation_avg_mw,
            wind_onshore_generation_avg_mw,
            wind_offshore_generation_avg_mw,
            total_renewable_generation_avg_mw,
            wholesale_price_eur_mwh,
            avg_wind_speed_ms,
            avg_air_temperature_c,
            avg_solar_radiation_j_cm2
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

    for column in [PRICE_COLUMN, *FEATURES.values()]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

        df[column] = df[column].replace(
            [np.inf, -np.inf],
            np.nan
        )

    return df


def validate_data(df):

    if len(df) != EXPECTED_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_HOURS} hours; "
            f"found {len(df)}."
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError(
            "Duplicate hourly timestamps detected."
        )

    expected = pd.date_range(
        "2026-09-01",
        periods=EXPECTED_HOURS,
        freq="h",
        tz="UTC"
    )

    if not df["interval_start_utc"].reset_index(
        drop=True
    ).equals(pd.Series(expected)):
        raise ValueError(
            "Hourly timestamp coverage is incorrect."
        )

    missing_prices = int(
        df[PRICE_COLUMN].isna().sum()
    )

    if missing_prices != EXPECTED_MISSING_PRICES:
        raise ValueError(
            f"Expected {EXPECTED_MISSING_PRICES} missing "
            f"prices; found {missing_prices}."
        )

    missing_features = df[
        list(FEATURES.values())
    ].isna().sum()

    if missing_features.any():
        raise ValueError(
            "Unexpected missing feature values:\n"
            f"{missing_features[missing_features > 0]}"
        )

    print("\nDATA VALIDATION")
    print("-" * 65)
    print(f"Hourly observations: {len(df)}")
    print(
        f"Available price observations: "
        f"{df[PRICE_COLUMN].notna().sum()}"
    )
    print(f"Missing prices: {missing_prices}")

    if missing_prices:
        print("Missing-price timestamps:")
        for timestamp in df.loc[
            df[PRICE_COLUMN].isna(),
            "interval_start_utc"
        ]:
            print(f"  {timestamp}")


def calculate_price_statistics(df):

    prices = df[PRICE_COLUMN].dropna()

    negative_hours = int((prices < 0).sum())
    zero_hours = int((prices == 0).sum())

    statistics = {
        "available_price_hours": len(prices),
        "missing_price_hours": int(
            df[PRICE_COLUMN].isna().sum()
        ),
        "average_price_eur_mwh": prices.mean(),
        "median_price_eur_mwh": prices.median(),
        "minimum_price_eur_mwh": prices.min(),
        "maximum_price_eur_mwh": prices.max(),
        "price_std_eur_mwh": prices.std(ddof=0),
        "negative_price_hours": negative_hours,
        "zero_price_hours": zero_hours,
        "negative_price_share_pct": (
            negative_hours / len(prices) * 100
        ),
        "p05_price_eur_mwh": prices.quantile(0.05),
        "p95_price_eur_mwh": prices.quantile(0.95),
    }

    return statistics


def calculate_correlations(df):

    results = []

    for label, column in FEATURES.items():

        valid = df[
            [PRICE_COLUMN, column]
        ].dropna()

        if (
            len(valid) < 3
            or valid[PRICE_COLUMN].nunique() < 2
            or valid[column].nunique() < 2
        ):
            correlation = float("nan")
        else:
            correlation = valid[
                PRICE_COLUMN
            ].corr(valid[column])

        results.append({
            "variable": label,
            "column": column,
            "observations": len(valid),
            "pearson_correlation": correlation,
        })

    return pd.DataFrame(results)


def calculate_hourly_profile(df):

    df = df.copy()

    df["hour_utc"] = (
        df["interval_start_utc"].dt.hour
    )

    profile = (
        df.groupby("hour_utc")
        .agg(
            average_price_eur_mwh=(
                PRICE_COLUMN,
                "mean"
            ),
            median_price_eur_mwh=(
                PRICE_COLUMN,
                "median"
            ),
            price_observations=(
                PRICE_COLUMN,
                "count"
            ),
            average_demand_mw=(
                "electricity_demand_mw",
                "mean"
            ),
            average_renewables_mw=(
                "total_renewable_generation_avg_mw",
                "mean"
            )
        )
        .reset_index()
    )

    return profile


def create_price_timeseries(df):

    fig, ax = plt.subplots(figsize=(13, 5))

    ax.plot(
        df["interval_start_utc"],
        df[PRICE_COLUMN],
        linewidth=1
    )

    ax.axhline(
        0,
        linestyle="--",
        linewidth=1,
        color="gray"
    )

    ax.set_title(
        "Hourly Wholesale Electricity Prices"
    )
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Wholesale price (EUR/MWh)")
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "01_hourly_prices.png",
        dpi=160
    )

    plt.close(fig)


def create_daily_price_profile(profile):

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        profile["hour_utc"],
        profile["average_price_eur_mwh"],
        marker="o"
    )

    ax.set_title(
        "Average Wholesale Price by UTC Hour"
    )
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Average price (EUR/MWh)")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "02_daily_price_profile.png",
        dpi=160
    )

    plt.close(fig)


def create_price_demand_scatter(df):

    valid = df[
        ["electricity_demand_mw", PRICE_COLUMN]
    ].dropna()

    fig, ax = plt.subplots(figsize=(9, 6))

    ax.scatter(
        valid["electricity_demand_mw"],
        valid[PRICE_COLUMN],
        alpha=0.4,
        s=20
    )

    ax.set_title(
        "Electricity Demand vs Wholesale Price"
    )
    ax.set_xlabel("Electricity demand (MW)")
    ax.set_ylabel("Wholesale price (EUR/MWh)")
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "03_price_vs_demand.png",
        dpi=160
    )

    plt.close(fig)


def create_price_renewables_scatter(df):

    valid = df[
        [
            "total_renewable_generation_avg_mw",
            PRICE_COLUMN
        ]
    ].dropna()

    fig, ax = plt.subplots(figsize=(9, 6))

    ax.scatter(
        valid["total_renewable_generation_avg_mw"],
        valid[PRICE_COLUMN],
        alpha=0.4,
        s=20
    )

    ax.set_title(
        "Renewable Generation vs Wholesale Price"
    )
    ax.set_xlabel(
        "Total renewable generation (MW)"
    )
    ax.set_ylabel(
        "Wholesale price (EUR/MWh)"
    )
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "04_price_vs_renewables.png",
        dpi=160
    )

    plt.close(fig)


def create_correlation_chart(correlations):

    ordered = correlations.sort_values(
        "pearson_correlation"
    )

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.barh(
        ordered["variable"],
        ordered["pearson_correlation"]
    )

    ax.axvline(
        0,
        color="gray",
        linewidth=1
    )

    ax.set_title(
        "Correlations with Wholesale Electricity Price"
    )
    ax.set_xlabel("Pearson correlation")
    ax.set_xlim(-1, 1)
    ax.grid(axis="x", alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "05_price_correlations.png",
        dpi=160
    )

    plt.close(fig)


def save_reports(
    statistics,
    correlations,
    hourly_profile
):

    pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in statistics.items()
        ]
    ).to_csv(
        OUTPUT_DIRECTORY / "price_statistics.csv",
        index=False
    )

    correlations.to_csv(
        OUTPUT_DIRECTORY / "price_correlations.csv",
        index=False
    )

    hourly_profile.to_csv(
        OUTPUT_DIRECTORY / "hourly_price_profile.csv",
        index=False
    )


def print_results(statistics, correlations):

    print("\n" + "=" * 65)
    print("WHOLESALE PRICE STATISTICS")
    print("=" * 65)

    for label, key in [
        ("Average price", "average_price_eur_mwh"),
        ("Median price", "median_price_eur_mwh"),
        ("Minimum price", "minimum_price_eur_mwh"),
        ("Maximum price", "maximum_price_eur_mwh"),
        ("Standard deviation", "price_std_eur_mwh"),
    ]:
        print(
            f"{label}: "
            f"EUR {statistics[key]:,.2f}/MWh"
        )

    print(
        f"Negative-price hours: "
        f"{statistics['negative_price_hours']}"
    )

    print(
        f"Negative-price share: "
        f"{statistics['negative_price_share_pct']:.2f}%"
    )

    print("\nCORRELATIONS WITH ELECTRICITY PRICE")
    print("-" * 65)

    for _, row in correlations.iterrows():

        value = row["pearson_correlation"]

        formatted = (
            f"{value:.4f}"
            if pd.notna(value)
            else "unavailable"
        )

        print(
            f"{row['variable']}: {formatted} "
            f"(n={int(row['observations'])})"
        )


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - ELECTRICITY PRICE ANALYTICS")
    print("=" * 65)

    df = load_data()

    validate_data(df)

    statistics = calculate_price_statistics(df)
    correlations = calculate_correlations(df)
    hourly_profile = calculate_hourly_profile(df)

    print_results(statistics, correlations)

    create_price_timeseries(df)
    create_daily_price_profile(hourly_profile)
    create_price_demand_scatter(df)
    create_price_renewables_scatter(df)
    create_correlation_chart(correlations)

    save_reports(
        statistics,
        correlations,
        hourly_profile
    )

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 12.5 completed successfully!")


if __name__ == "__main__":
    main()
