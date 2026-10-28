
import sqlite3
from pathlib import Path

import pandas as pd

# ============================================================
# INNEVA.E - ENERGY MARKET OVERVIEW
# MODULE 12 | CHECKPOINT 12.1
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "energy_market_overview.csv"
)

EXPECTED_HOURS = 720
HOURS_PER_INTERVAL = 1.0


def load_energy_data():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    query = """
        SELECT
            interval_start_utc,
            electricity_demand_mw,
            demand_forecast_mw,
            solar_generation_avg_mw,
            wind_onshore_generation_avg_mw,
            wind_offshore_generation_avg_mw,
            total_renewable_generation_avg_mw,
            wholesale_price_eur_mwh
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

    return df


def validate_data(df):

    if len(df) != EXPECTED_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_HOURS} hours, "
            f"found {len(df)}"
        )

    if df["interval_start_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps detected.")

    required_columns = [
        "electricity_demand_mw",
        "solar_generation_avg_mw",
        "wind_onshore_generation_avg_mw",
        "wind_offshore_generation_avg_mw",
        "total_renewable_generation_avg_mw",
    ]

    if df[required_columns].isna().any().any():
        raise ValueError(
            "Missing values in required energy columns."
        )

    if (df[required_columns] < 0).any().any():
        raise ValueError(
            "Negative values detected in energy columns."
        )

    print("Data validation passed.")
    print(f"Hourly observations: {len(df)}")
    print(
        "Missing wholesale prices:",
        df["wholesale_price_eur_mwh"].isna().sum()
    )


def calculate_kpis(df):

    # Power (MW) multiplied by time (hours) gives energy (MWh).
    # Divide by 1000 to convert MWh to GWh.

    demand_gwh = (
        df["electricity_demand_mw"].sum()
        * HOURS_PER_INTERVAL
        / 1000
    )

    solar_gwh = (
        df["solar_generation_avg_mw"].sum()
        * HOURS_PER_INTERVAL
        / 1000
    )

    wind_onshore_gwh = (
        df["wind_onshore_generation_avg_mw"].sum()
        * HOURS_PER_INTERVAL
        / 1000
    )

    wind_offshore_gwh = (
        df["wind_offshore_generation_avg_mw"].sum()
        * HOURS_PER_INTERVAL
        / 1000
    )

    renewable_gwh = (
        df["total_renewable_generation_avg_mw"].sum()
        * HOURS_PER_INTERVAL
        / 1000
    )

    renewable_ratio = (
        renewable_gwh / demand_gwh * 100
        if demand_gwh > 0
        else float("nan")
    )

    # Mean of available hourly wholesale prices.
    # Missing prices remain excluded, not replaced with zero.

    average_price = df[
        "wholesale_price_eur_mwh"
    ].mean()

    minimum_price = df[
        "wholesale_price_eur_mwh"
    ].min()

    maximum_price = df[
        "wholesale_price_eur_mwh"
    ].max()

    kpis = {
        "electricity_demand_gwh": demand_gwh,
        "solar_generation_gwh": solar_gwh,
        "wind_onshore_generation_gwh": wind_onshore_gwh,
        "wind_offshore_generation_gwh": wind_offshore_gwh,
        "total_renewable_generation_gwh": renewable_gwh,
        "renewable_generation_to_demand_pct": renewable_ratio,
        "average_wholesale_price_eur_mwh": average_price,
        "minimum_wholesale_price_eur_mwh": minimum_price,
        "maximum_wholesale_price_eur_mwh": maximum_price,
        "available_price_observations": int(
            df["wholesale_price_eur_mwh"].count()
        ),
    }

    return kpis


def print_report(kpis):

    print("\n" + "=" * 65)
    print("INNEVA.E - SEPTEMBER 2026 ENERGY MARKET OVERVIEW")
    print("=" * 65)

    print("\nELECTRICITY DEMAND")
    print("-" * 65)
    print(
        f"Total electricity demand: "
        f"{kpis['electricity_demand_gwh']:,.2f} GWh"
    )

    print("\nRENEWABLE GENERATION")
    print("-" * 65)
    print(
        f"Solar: "
        f"{kpis['solar_generation_gwh']:,.2f} GWh"
    )
    print(
        f"Onshore wind: "
        f"{kpis['wind_onshore_generation_gwh']:,.2f} GWh"
    )
    print(
        f"Offshore wind: "
        f"{kpis['wind_offshore_generation_gwh']:,.2f} GWh"
    )
    print(
        f"Total renewable generation: "
        f"{kpis['total_renewable_generation_gwh']:,.2f} GWh"
    )

    print("\nRENEWABLE CONTRIBUTION")
    print("-" * 65)
    print(
        "Renewable generation-to-demand ratio: "
        f"{kpis['renewable_generation_to_demand_pct']:.2f}%"
    )

    print("\nWHOLESALE ELECTRICITY PRICES")
    print("-" * 65)
    print(
        f"Average price: "
        f"€{kpis['average_wholesale_price_eur_mwh']:,.2f}/MWh"
    )
    print(
        f"Minimum price: "
        f"€{kpis['minimum_wholesale_price_eur_mwh']:,.2f}/MWh"
    )
    print(
        f"Maximum price: "
        f"€{kpis['maximum_wholesale_price_eur_mwh']:,.2f}/MWh"
    )
    print(
        f"Available price observations: "
        f"{kpis['available_price_observations']}"
    )


def save_report(kpis):

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report_df = pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in kpis.items()
        ]
    )

    report_df.to_csv(
        OUTPUT_PATH,
        index=False
    )

    print(f"\nReport saved to: {OUTPUT_PATH}")


def main():

    print("=" * 65)
    print("INNEVA.E - ENERGY MARKET ANALYTICS")
    print("=" * 65)

    df = load_energy_data()

    validate_data(df)

    kpis = calculate_kpis(df)

    print_report(kpis)

    save_report(kpis)

    print("\nCheckpoint 12.1 calculations completed!")


if __name__ == "__main__":
    main()
