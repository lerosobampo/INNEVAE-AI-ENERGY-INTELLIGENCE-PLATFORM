
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - PRECIPITATION DIAGNOSTICS
# CHECKPOINT 11.15
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)


def inspect_precipitation():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    with sqlite3.connect(DATABASE_PATH) as connection:

        print("=" * 65)
        print("INNEVA.E PRECIPITATION DIAGNOSTICS")
        print("=" * 65)

        # ----------------------------------------------------
        # 1. SOURCE DATA DISTRIBUTION
        # ----------------------------------------------------

        print("\n1. ORIGINAL PRECIPITATION VALUES")
        print("-" * 65)

        result = connection.execute("""
            SELECT
                MIN(precipitation_amount_0_1_mm),
                MAX(precipitation_amount_0_1_mm),
                COUNT(
                    CASE
                        WHEN precipitation_amount_0_1_mm < 0
                        THEN 1
                    END
                ),
                COUNT(
                    CASE
                        WHEN precipitation_amount_0_1_mm = 0
                        THEN 1
                    END
                ),
                COUNT(
                    CASE
                        WHEN precipitation_amount_0_1_mm > 0
                        THEN 1
                    END
                )
            FROM weather_observations
        """).fetchone()

        print(f"Minimum raw value: {result[0]}")
        print(f"Maximum raw value: {result[1]}")
        print(f"Negative observations: {result[2]}")
        print(f"Zero observations: {result[3]}")
        print(f"Positive observations: {result[4]}")

        # ----------------------------------------------------
        # 2. NEGATIVE SOURCE OBSERVATIONS
        # ----------------------------------------------------

        print("\n2. NEGATIVE SOURCE VALUES")
        print("-" * 65)

        negative_values = connection.execute("""
            SELECT
                precipitation_amount_0_1_mm,
                COUNT(*) AS occurrences
            FROM weather_observations
            WHERE precipitation_amount_0_1_mm < 0
            GROUP BY precipitation_amount_0_1_mm
            ORDER BY precipitation_amount_0_1_mm
        """).fetchall()

        if negative_values:
            for value, count in negative_values:
                print(
                    f"Raw value {value}: "
                    f"{count} observations"
                )
        else:
            print("No negative source values found.")

        # ----------------------------------------------------
        # 3. INVALID HOURLY AVERAGES
        # ----------------------------------------------------

        print("\n3. HOURLY AVERAGES OUTSIDE VALIDATION RANGE")
        print("-" * 65)

        invalid_hours = connection.execute("""
            SELECT
                interval_start_utc,
                avg_precipitation_mm,
                precipitation_reporting_stations
            FROM hourly_weather_summary
            WHERE avg_precipitation_mm < 0
               OR avg_precipitation_mm > 500
            ORDER BY interval_start_utc
        """).fetchall()

        print(f"Invalid hourly averages: {len(invalid_hours)}")

        for row in invalid_hours[:20]:
            print(row)

        # ----------------------------------------------------
        # 4. SAMPLE NEGATIVE OBSERVATIONS
        # ----------------------------------------------------

        print("\n4. SAMPLE NEGATIVE STATION OBSERVATIONS")
        print("-" * 65)

        examples = connection.execute("""
            SELECT
                interval_start_utc,
                station_id,
                precipitation_amount_0_1_mm,
                precipitation_duration_0_1_hours
            FROM weather_observations
            WHERE precipitation_amount_0_1_mm < 0
            ORDER BY interval_start_utc, station_id
            LIMIT 15
        """).fetchall()

        if examples:
            for row in examples:
                print(row)
        else:
            print("No negative observations found.")

        print("\nDiagnostic completed.")


if __name__ == "__main__":
    inspect_precipitation()
