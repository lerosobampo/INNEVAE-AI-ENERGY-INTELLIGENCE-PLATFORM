
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ============================================================
# INNEVA.E - RENEWABLE GENERATION ANALYSIS
# MODULE 12 | CHECKPOINT 12.3
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "renewable_analysis"
)

EXPECTED_HOURS = 720

GENERATION_COLUMNS = {
    "Solar": "solar_generation_avg_mw",
    "Onshore wind": "wind_onshore_generation_avg_mw",
    "Offshore wind": "wind_offshore_generation_avg_mw",
}


def load_data():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    query = """
        SELECT
            interval_start_utc,
            electricity_demand_mw,
            solar_generation_avg_mw,
            wind_onshore_generation_avg_mw,
            wind_offshore_generation_avg_mw,
            total_renewable_generation_avg_mw
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

    required_columns = [
        "electricity_demand_mw",
        *GENERATION_COLUMNS.values(),
        "total_renewable_generation_avg_mw",
    ]

    if len(df) != EXPECTED_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_HOURS} records, found {len(df)}"
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError("Duplicate hourly timestamps detected.")

    expected_timestamps = pd.date_range(
        start="2026-09-01",
        periods=EXPECTED_HOURS,
        freq="h",
        tz="UTC"
    )

    if not df["interval_start_utc"].reset_index(
        drop=True
    ).equals(pd.Series(expected_timestamps)):
        raise ValueError(
            "Incomplete or incorrectly ordered hourly timestamps."
        )

    if df[required_columns].isna().any().any():
        raise ValueError(
            "Missing demand or renewable generation values."
        )

    if not np.isfinite(
        df[required_columns].to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Non-finite numerical values detected."
        )

    if (df[required_columns] < 0).any().any():
        raise ValueError(
            "Negative demand or renewable generation detected."
        )

    calculated_total = df[
        list(GENERATION_COLUMNS.values())
    ].sum(axis=1)

    if not np.allclose(
        calculated_total,
        df["total_renewable_generation_avg_mw"],
        rtol=1e-9,
        atol=1e-6
    ):
        raise ValueError(
            "Renewable generation components do not match total."
        )

    df["hour_utc"] = df["interval_start_utc"].dt.hour

    df["date_utc"] = df[
        "interval_start_utc"
    ].dt.date

    return df


def calculate_statistics(df):

    results = []

    total_generation_mwh = (
        df["total_renewable_generation_avg_mw"].sum()
    )

    for technology, column in GENERATION_COLUMNS.items():

        series = df[column]

        generation_gwh = series.sum() / 1000

        share = (
            series.sum() / total_generation_mwh * 100
            if total_generation_mwh > 0
            else float("nan")
        )

        mean = series.mean()

        std = series.std(ddof=0)

        coefficient_of_variation = (
            std / mean * 100
            if mean > 0
            else float("nan")
        )

        results.append({
            "technology": technology,
            "generation_gwh": generation_gwh,
            "renewable_share_pct": share,
            "average_generation_mw": mean,
            "maximum_generation_mw": series.max(),
            "minimum_generation_mw": series.min(),
            "standard_deviation_mw": std,
            "coefficient_of_variation_pct":
                coefficient_of_variation,
        })

    statistics = pd.DataFrame(results)

    total_demand_gwh = (
        df["electricity_demand_mw"].sum() / 1000
    )

    total_renewable_gwh = (
        df["total_renewable_generation_avg_mw"].sum()
        / 1000
    )

    summary = {
        "total_demand_gwh": total_demand_gwh,
        "total_renewable_generation_gwh":
            total_renewable_gwh,
        "renewable_generation_to_demand_pct": (
            total_renewable_gwh / total_demand_gwh * 100
            if total_demand_gwh > 0
            else float("nan")
        ),
        "peak_renewable_generation_mw": df[
            "total_renewable_generation_avg_mw"
        ].max(),
        "average_renewable_generation_mw": df[
            "total_renewable_generation_avg_mw"
        ].mean(),
    }

    return statistics, summary


def create_generation_breakdown(statistics):

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.bar(
        statistics["technology"],
        statistics["generation_gwh"]
    )

    ax.set_title(
        "Renewable Electricity Generation by Technology"
    )

    ax.set_xlabel("Technology")
    ax.set_ylabel("Monthly generation (GWh)")
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "01_generation_breakdown.png",
        dpi=160
    )

    plt.close(fig)


def create_hourly_generation_chart(df):

    fig, ax = plt.subplots(figsize=(13, 5))

    for technology, column in GENERATION_COLUMNS.items():

        ax.plot(
            df["interval_start_utc"],
            df[column],
            linewidth=1,
            label=technology
        )

    ax.set_title(
        "Hourly Renewable Generation - September 2026"
    )

    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Average generation (MW)")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "02_hourly_generation.png",
        dpi=160
    )

    plt.close(fig)


def create_solar_daily_profile(df):

    profile = df.groupby(
        "hour_utc"
    )["solar_generation_avg_mw"].mean()

    fig, ax = plt.subplots(figsize=(11, 5))

    ax.plot(
        profile.index,
        profile.values,
        marker="o"
    )

    ax.set_title(
        "Average Solar Generation by Hour"
    )

    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Average solar generation (MW)")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "03_solar_daily_profile.png",
        dpi=160
    )

    plt.close(fig)


def create_generation_variability(statistics):

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.bar(
        statistics["technology"],
        statistics["coefficient_of_variation_pct"]
    )

    ax.set_title(
        "Renewable Generation Variability"
    )

    ax.set_xlabel("Technology")
    ax.set_ylabel("Coefficient of variation (%)")
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "04_generation_variability.png",
        dpi=160
    )

    plt.close(fig)


def create_renewable_demand_chart(df):

    fig, ax = plt.subplots(figsize=(13, 5))

    ax.plot(
        df["interval_start_utc"],
        df["electricity_demand_mw"],
        label="Electricity demand",
        linewidth=1
    )

    ax.plot(
        df["interval_start_utc"],
        df["total_renewable_generation_avg_mw"],
        label="Renewable generation",
        linewidth=1
    )

    ax.set_title(
        "Electricity Demand vs Renewable Generation"
    )

    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Average power (MW)")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "05_renewables_vs_demand.png",
        dpi=160
    )

    plt.close(fig)


def save_reports(statistics, summary):

    statistics.to_csv(
        OUTPUT_DIRECTORY / "renewable_statistics.csv",
        index=False
    )

    summary_df = pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in summary.items()
        ]
    )

    summary_df.to_csv(
        OUTPUT_DIRECTORY / "renewable_summary.csv",
        index=False
    )


def print_results(statistics, summary):

    print("\n" + "=" * 65)
    print("RENEWABLE GENERATION ANALYSIS")
    print("=" * 65)

    print("\nGENERATION BY TECHNOLOGY")
    print("-" * 65)

    for _, row in statistics.iterrows():

        print(
            f"{row['technology']}: "
            f"{row['generation_gwh']:,.2f} GWh "
            f"({row['renewable_share_pct']:.2f}%)"
        )

    print("\nGENERATION VARIABILITY")
    print("-" * 65)

    for _, row in statistics.iterrows():

        print(
            f"{row['technology']}: "
            f"CV = "
            f"{row['coefficient_of_variation_pct']:.2f}%"
        )

    print("\nRENEWABLE CONTRIBUTION")
    print("-" * 65)

    print(
        f"Total renewable generation: "
        f"{summary['total_renewable_generation_gwh']:,.2f} GWh"
    )

    print(
        f"Electricity demand: "
        f"{summary['total_demand_gwh']:,.2f} GWh"
    )

    print(
        f"Generation-to-demand ratio: "
        f"{summary['renewable_generation_to_demand_pct']:.2f}%"
    )

    print(
        f"Peak renewable generation: "
        f"{summary['peak_renewable_generation_mw']:,.2f} MW"
    )


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - RENEWABLE ENERGY ANALYTICS")
    print("=" * 65)

    df = load_data()

    print(f"Data loaded: {len(df)} hourly observations")

    statistics, summary = calculate_statistics(df)

    print_results(statistics, summary)

    create_generation_breakdown(statistics)
    create_hourly_generation_chart(df)
    create_solar_daily_profile(df)
    create_generation_variability(statistics)
    create_renewable_demand_chart(df)

    save_reports(statistics, summary)

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 12.3 completed successfully!")


if __name__ == "__main__":
    main()
