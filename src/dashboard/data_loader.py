
"""
INNEVA.E - DASHBOARD DATA LOADER
Module 16 - Checkpoint 16.2

Responsibilities:
- Connect to the existing SQLite database
- Inspect the analytical view schema
- Load historical energy observations
- Validate required fields
- Prepare data for Streamlit visualizations

All database operations are read-only.
"""

import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "innevae_platform.db"
)

VIEW_NAME = "integrated_energy_intelligence_imputed"


def get_database_connection():
    """
    Open the existing SQLite database in read-only mode.
    """

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    database_uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"

    return sqlite3.connect(
        database_uri,
        uri=True,
    )


def inspect_view_columns():
    """
    Return the column names of the analytical view.
    """

    with get_database_connection() as connection:
        rows = connection.execute(
            f"PRAGMA table_info({VIEW_NAME})"
        ).fetchall()

    return [row[1] for row in rows]


def load_energy_data():
    """
    Load the analytical view into a Pandas DataFrame.

    The exact schema is inspected first so that
    we can detect mismatches explicitly.
    """

    columns = inspect_view_columns()

    if not columns:
        raise ValueError(
            f"Analytical view not found: {VIEW_NAME}"
        )

    with get_database_connection() as connection:
        data = pd.read_sql_query(
            f"SELECT * FROM {VIEW_NAME}",
            connection,
        )

    if data.empty:
        raise ValueError(
            "The analytical view returned no observations."
        )

    return data


def describe_energy_schema():
    """
    Print the view columns and example observations.
    """

    data = load_energy_data()

    print("=" * 65)
    print("INNEVA.E - DASHBOARD DATA INSPECTION")
    print("=" * 65)

    print("\nDatabase:")
    print(DATABASE_PATH)

    print("\nAnalytical view:")
    print(VIEW_NAME)

    print("\nRows:", len(data))

    print("\nColumns:")
    for column in data.columns:
        print(f"  - {column}")

    print("\nFirst 3 observations:")
    print(
        data.head(3).to_string(index=False)
    )

    print("\nData types:")
    print(data.dtypes.to_string())


if __name__ == "__main__":
    describe_energy_schema()
