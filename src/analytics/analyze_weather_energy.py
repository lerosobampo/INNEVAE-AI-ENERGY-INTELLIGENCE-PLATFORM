
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ============================================================
# INNEVA.E - WEATHER AND ENERGY RELATIONSHIPS
# MODULE 12 | CHECKPOINT 12.4
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "weather_energy_analysis"
)

EXPECTED_HOURS = 720

RELATIONSHIPS = [
    {
        "name": "Wind speed vs onshore generation",
        "x": "avg_wind_speed_ms",
        "y": "wind_onshore_generation_avg_mw",
        "filename": "01_wind_onshore_scatter.png",
        "xlabel": "Average station wind speed (m/s)",
        "ylabel": "Onshore generation (MW)",
    },
    {
        "name": "Wind speed vs offshore generation",
        "x": "avg_wind_speed_ms",
        "y": "wind_offshore_generation_avg_mw",
        "filename": "02_wind_offshore_scatter.png",
        "xlabel": "Average station wind speed (m/s)",
        "ylabel": "Offshore generation (MW)",
    },
    {
        "name": "Solar radiation vs solar generation",
        "x": "avg_solar_radiation_j_cm2",
        "y": "solar_generation_avg_mw",
        "filename": "03_solar_radiation_scatter.png",
        "xlabel": "Average solar radiation (J/cm²)",
        "ylabel": "Solar generation (MW)",
    },
    {
        "name": "Temperature vs electricity demand",
        "x": "avg_air_temperature_c",
        "y": "electricity_demand_mw",
        "filename": "04_temperature_demand_scatter.png",
        "xlabel": "Average station temperature (°C)",
        "ylabel": "Electricity demand (MW)",
    },
]


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
            avg_wind_speed_ms,
            avg_air_temperature_c,
            avg_solar_radiation_j_cm2,
            wind_reporting_stations,
            temperature_reporting_stations,
            solar_reporting_stations
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

    numeric_columns = [
        column
        for relationship in RELATIONSHIPS
        for column in (
            relationship["x"],
            relationship["y"]
        )
    ]

    numeric_columns = list(set(numeric_columns))

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

        df.loc[
            ~np.isfinite(df[column]),
            column
        ] = np.nan

    print("Data validation passed.")
    print(f"Hourly observations: {len(df)}")

    for column in numeric_columns:
        print(
            f"Missing {column}: "
            f"{df[column].isna().sum()}"
        )


def calculate_correlations(df):

    results = []

    for relationship in RELATIONSHIPS:

        x = relationship["x"]
        y = relationship["y"]

        valid = df[[x, y]].dropna()

        if (
            len(valid) < 3
            or valid[x].nunique() < 2
            or valid[y].nunique() < 2
        ):
            correlation = float("nan")
        else:
            correlation = valid[x].corr(
                valid[y],
                method="pearson"
            )

        results.append({
            "relationship": relationship["name"],
            "weather_variable": x,
            "energy_variable": y,
            "observations": len(valid),
            "pearson_correlation": correlation,
        })

    return pd.DataFrame(results)


def create_scatter_plots(df):

    for relationship in RELATIONSHIPS:

        x = relationship["x"]
        y = relationship["y"]

        valid = df[[x, y]].dropna()

        fig, ax = plt.subplots(figsize=(9, 6))

        ax.scatter(
            valid[x],
            valid[y],
            alpha=0.4,
            s=20
        )

        ax.set_title(relationship["name"])
        ax.set_xlabel(relationship["xlabel"])
        ax.set_ylabel(relationship["ylabel"])
        ax.grid(alpha=0.3)

        fig.tight_layout()

        fig.savefig(
            OUTPUT_DIRECTORY / relationship["filename"],
            dpi=160
        )

        plt.close(fig)


def create_correlation_heatmap(df):

    columns = [
        "electricity_demand_mw",
        "solar_generation_avg_mw",
        "wind_onshore_generation_avg_mw",
        "wind_offshore_generation_avg_mw",
        "avg_wind_speed_ms",
        "avg_air_temperature_c",
        "avg_solar_radiation_j_cm2",
    ]

    matrix = df[columns].corr(
        method="pearson"
    )

    fig, ax = plt.subplots(figsize=(11, 9))

    image = ax.imshow(
        matrix,
        cmap="coolwarm",
        vmin=-1,
        vmax=1
    )

    labels = [
        "Demand",
        "Solar",
        "Onshore wind",
        "Offshore wind",
        "Wind speed",
        "Temperature",
        "Solar radiation",
    ]

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))

    ax.set_xticklabels(
        labels,
        rotation=45,
        ha="right"
    )

    ax.set_yticklabels(labels)

    for i in range(len(labels)):
        for j in range(len(labels)):
            value = matrix.iloc[i, j]

            label = (
                f"{value:.2f}"
                if pd.notna(value)
                else "N/A"
            )

            ax.text(
                j,
                i,
                label,
                ha="center",
                va="center",
                fontsize=9,
                color=(
                    "white"
                    if pd.notna(value)
                    and abs(value) > 0.65
                    else "black"
                )
            )

    fig.colorbar(
        image,
        ax=ax,
        label="Pearson correlation"
    )

    ax.set_title(
        "Energy and Weather Correlation Matrix"
    )

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIRECTORY / "05_correlation_heatmap.png",
        dpi=160
    )

    plt.close(fig)

    return matrix


def save_reports(correlations, matrix):

    correlations.to_csv(
        OUTPUT_DIRECTORY / "weather_energy_correlations.csv",
        index=False
    )

    matrix.to_csv(
        OUTPUT_DIRECTORY / "full_correlation_matrix.csv"
    )


def print_results(correlations):

    print("\n" + "=" * 65)
    print("WEATHER AND ENERGY CORRELATIONS")
    print("=" * 65)

    for _, row in correlations.iterrows():

        print(f"\n{row['relationship']}")
        print("-" * 65)

        print(
            f"Observations: {int(row['observations'])}"
        )

        correlation = row["pearson_correlation"]

        if pd.isna(correlation):
            print("Pearson correlation: unavailable")
        else:
            print(
                f"Pearson correlation: {correlation:.4f}"
            )


def main():

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 65)
    print("INNEVA.E - WEATHER AND ENERGY ANALYTICS")
    print("=" * 65)

    df = load_data()

    validate_data(df)

    correlations = calculate_correlations(df)

    print_results(correlations)

    create_scatter_plots(df)

    matrix = create_correlation_heatmap(df)

    save_reports(correlations, matrix)

    print("\nOUTPUT FILES")
    print("-" * 65)

    for file in sorted(OUTPUT_DIRECTORY.iterdir()):
        print(file.name)

    print("\nCheckpoint 12.4 completed successfully!")


if __name__ == "__main__":
    main()
