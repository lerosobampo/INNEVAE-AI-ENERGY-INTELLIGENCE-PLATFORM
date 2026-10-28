
"""
INNEVA.E — Unified Dataset Audit
Checkpoint 17.8A

Read-only inspection of:
1. SQLite tables and views
2. Historical forecasting CSV
3. Latest 90-day coverage
4. Column structures and timestamp integrity

No data or model files are modified.
"""

from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

HISTORICAL_CSV = (
    DATA_DIR
    / "forecasting"
    / "energy_intelligence_hourly.csv"
)

START = pd.Timestamp("2026-07-03", tz="UTC")
END = pd.Timestamp("2026-10-01", tz="UTC")
EXPECTED_HOURS = 2160

TIMESTAMP_CANDIDATES = [
    "hour_start_utc",
    "interval_start_utc",
    "timestamp_utc",
    "datetime_utc",
    "timestamp",
]


def inspect_csv():
    print("\n" + "=" * 65)
    print("1. HISTORICAL FORECASTING CSV")
    print("=" * 65)

    if not HISTORICAL_CSV.exists():
        print("NOT FOUND:", HISTORICAL_CSV)
        return

    df = pd.read_csv(HISTORICAL_CSV)

    print("File:", HISTORICAL_CSV)
    print("Total rows:", len(df))
    print("Columns:", len(df.columns))

    print("\nCOLUMN STRUCTURE")
    for name, dtype in df.dtypes.items():
        print(f"  {name}: {dtype}")

    timestamp_col = next(
        (
            name
            for name in TIMESTAMP_CANDIDATES
            if name in df.columns
        ),
        None,
    )

    if timestamp_col is None:
        print("\nWARNING: No recognized timestamp column.")
        return

    timestamps = pd.to_datetime(
        df[timestamp_col],
        utc=True,
        errors="coerce",
    )

    print("\nHISTORICAL COVERAGE")
    print("First timestamp:", timestamps.min())
    print("Last timestamp:", timestamps.max())
    print("Invalid timestamps:", timestamps.isna().sum())

    window = df.loc[
        (timestamps >= START)
        & (timestamps < END)
    ].copy()

    window_times = timestamps.loc[window.index]

    expected_index = pd.date_range(
        START,
        periods=EXPECTED_HOURS,
        freq="h",
    )

    unique_times = pd.DatetimeIndex(
        window_times.dropna().unique()
    )

    missing = expected_index.difference(unique_times)

    print("\n90-DAY DEVELOPMENT WINDOW")
    print("Start:", START)
    print("End exclusive:", END)
    print("Expected hourly records:", EXPECTED_HOURS)
    print("Actual records:", len(window))
    print("Unique timestamps:", len(unique_times))
    print("Missing hourly timestamps:", len(missing))
    print(
        "Duplicate hourly timestamps:",
        int(window_times.duplicated().sum()),
    )

    if len(missing):
        print("First missing timestamps:")
        for value in missing[:5]:
            print(" ", value)

    print("\n90-DAY NULL COUNTS")
    print(window.isna().sum().to_string())


def inspect_sqlite():
    print("\n" + "=" * 65)
    print("2. SQLITE DATABASE DISCOVERY")
    print("=" * 65)

    databases = sorted(
        {
            path
            for pattern in ("*.db", "*.sqlite", "*.sqlite3")
            for path in DATA_DIR.rglob(pattern)
        }
    )

    if not databases:
        print("No SQLite databases found.")
        return

    for db_path in databases:
        print("\nDATABASE:", db_path)

        # Read-only connection: prevents accidental writes.
        uri = db_path.resolve().as_uri() + "?mode=ro"

        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
            )

            objects = pd.read_sql_query(
                """
                SELECT name, type
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """,
                connection,
            )

            if objects.empty:
                print("No user tables or views.")
                connection.close()
                continue

            print("\nTABLES AND VIEWS")
            print(objects.to_string(index=False))

            for _, item in objects.iterrows():
                name = item["name"]

                escaped = name.replace('"', '""')

                columns = pd.read_sql_query(
                    f'PRAGMA table_info("{escaped}")',
                    connection,
                )

                column_names = columns["name"].tolist()

                print(f"\nOBJECT: {name}")
                print("Type:", item["type"])
                print("Columns:", ", ".join(column_names))

                timestamp_col = next(
                    (
                        candidate
                        for candidate in TIMESTAMP_CANDIDATES
                        if candidate in column_names
                    ),
                    None,
                )

                if timestamp_col is None:
                    print(
                        "No recognized timestamp column; "
                        "coverage check skipped."
                    )
                    continue

                quoted_ts = (
                    '"' + timestamp_col.replace('"', '""') + '"'
                )

                try:
                    result = pd.read_sql_query(
                        f"""
                        SELECT
                            COUNT(*) AS total_rows,
                            MIN({quoted_ts}) AS first_timestamp,
                            MAX({quoted_ts}) AS last_timestamp
                        FROM "{escaped}"
                        """,
                        connection,
                    )

                    print("Coverage:")
                    print(result.to_string(index=False))

                    # Read the timestamp column only.
                    time_data = pd.read_sql_query(
                        f'SELECT {quoted_ts} FROM "{escaped}"',
                        connection,
                    )

                    timestamps = pd.to_datetime(
                        time_data[timestamp_col],
                        utc=True,
                        errors="coerce",
                    )

                    window_times = timestamps.loc[
                        (timestamps >= START)
                        & (timestamps < END)
                    ]

                    expected_index = pd.date_range(
                        START,
                        periods=EXPECTED_HOURS,
                        freq="h",
                    )

                    unique_times = pd.DatetimeIndex(
                        window_times.dropna().unique()
                    )

                    missing = expected_index.difference(
                        unique_times
                    )

                    print("90-day rows:", len(window_times))
                    print(
                        "90-day unique timestamps:",
                        len(unique_times),
                    )
                    print(
                        "90-day missing hours:",
                        len(missing),
                    )
                    print(
                        "90-day duplicate hours:",
                        int(window_times.duplicated().sum()),
                    )

                except Exception as error:
                    print(
                        "Could not inspect coverage:",
                        error,
                    )

            connection.close()

        except Exception as error:
            print("Database inspection failed:", error)


def main():
    print("\nINNEVA.E — UNIFIED 90-DAY DATASET AUDIT")
    print("Read-only verification")
    print("Development window: July 3–September 30, 2026")

    inspect_csv()
    inspect_sqlite()

    print("\n" + "=" * 65)
    print("AUDIT COMPLETE")
    print("=" * 65)
    print(
        "No data, model, or database files were modified."
    )


if __name__ == "__main__":
    main()
