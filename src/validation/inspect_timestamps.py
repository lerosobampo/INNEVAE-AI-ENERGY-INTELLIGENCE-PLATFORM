
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - TIMESTAMP FORMAT INSPECTION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

TIME_COLUMNS = {
    "electricity_demand": "interval_start_utc",
    "solar_generation": "valid_from_utc",
    "wind_onshore_generation": "valid_from_utc",
    "wind_offshore_generation": "valid_from_utc",
    "weather_observations": "interval_start_utc",
    "wholesale_prices": "interval_start_utc",
}


def inspect_timestamps():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    print("\nINNEVA.E TIMESTAMP INSPECTION")
    print("=" * 60)

    with sqlite3.connect(DATABASE_PATH) as connection:

        for table, column in TIME_COLUMNS.items():

            print(f"\nTABLE: {table}")
            print("-" * 60)

            query = (
                f'SELECT "{column}" '
                f'FROM "{table}" '
                f'ORDER BY "{column}" '
                f'LIMIT 3'
            )

            rows = connection.execute(query).fetchall()

            for index, (value,) in enumerate(rows, start=1):

                print(f"Sample {index}: {repr(value)}")
                print(f"Python type: {type(value).__name__}")

            minimum, maximum = connection.execute(
                f'''
                SELECT MIN("{column}"), MAX("{column}")
                FROM "{table}"
                '''
            ).fetchone()

            print(f"Earliest stored value: {minimum}")
            print(f"Latest stored value:   {maximum}")


if __name__ == "__main__":
    inspect_timestamps()
