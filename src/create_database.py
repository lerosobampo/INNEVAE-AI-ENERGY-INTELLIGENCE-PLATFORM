
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - DATABASE INITIALIZATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

SCHEMA_PATH = (
    PROJECT_ROOT / "src" / "database" / "schema.sql"
)

EXPECTED_TABLES = {
    "electricity_demand",
    "solar_generation",
    "wind_onshore_generation",
    "wind_offshore_generation",
    "weather_observations",
    "wholesale_prices",
    "grid_capacity",
}


def create_database():

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(
            f"Schema file not found: {SCHEMA_PATH}"
        )

    schema_sql = SCHEMA_PATH.read_text(
        encoding="utf-8"
    )

    if not schema_sql.strip():
        raise ValueError("The schema.sql file is empty.")

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        connection.executescript(schema_sql)

        connection.commit()

        cursor = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
        """)

        tables = {
            row[0]
            for row in cursor.fetchall()
        }

        missing_tables = EXPECTED_TABLES - tables

        if missing_tables:
            raise RuntimeError(
                f"Missing tables: {sorted(missing_tables)}"
            )

        demand_count = connection.execute(
            "SELECT COUNT(*) FROM electricity_demand"
        ).fetchone()[0]

        print("\nDATABASE INITIALIZED SUCCESSFULLY")
        print("=" * 50)

        print(f"Database: {DATABASE_PATH.name}")
        print(f"Total tables: {len(tables)}")

        print("\nAvailable tables:")

        for table in sorted(tables):
            print(f" - {table}")

        print(
            f"\nExisting electricity demand records: "
            f"{demand_count:,}"
        )


if __name__ == "__main__":
    create_database()
