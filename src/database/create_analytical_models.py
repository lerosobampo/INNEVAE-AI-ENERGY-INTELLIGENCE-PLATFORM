
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - ANALYTICAL DATA MODEL
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

VIEW_NAME = "hourly_energy_model"

EXPECTED_HOURS = 720


def create_analytical_model():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    with sqlite3.connect(DATABASE_PATH) as connection:

        # Check whether each source has one row per hour.
        source_checks = {
            "electricity_demand": "interval_start_utc",
            "solar_generation": "valid_from_utc",
            "wind_onshore_generation": "valid_from_utc",
            "wind_offshore_generation": "valid_from_utc",
            "wholesale_prices": "interval_start_utc",
        }

        print("\nSOURCE GRAIN VALIDATION")
        print("=" * 55)

        for table, time_column in source_checks.items():

            total, distinct = connection.execute(
                f"""
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT "{time_column}")
                FROM "{table}"
                """
            ).fetchone()

            print(
                f"{table}: {total} records, "
                f"{distinct} distinct hours"
            )

            if total != distinct:
                raise ValueError(
                    f"{table} has multiple records per hour. "
                    "An aggregation strategy is required."
                )

        # Create a view without changing source data.
        connection.execute(
            f'DROP VIEW IF EXISTS "{VIEW_NAME}"'
        )

        connection.execute("""
            CREATE VIEW hourly_energy_model AS

            SELECT
                datetime(d.interval_start_utc)
                    AS interval_start_utc,

                d.area,

                d.actual_total_load_mw
                    AS electricity_demand_mw,

                d.day_ahead_total_load_forecast_mw
                    AS demand_forecast_mw,

                s.capacity_kw
                    AS solar_capacity_kw,

                s.volume_kwh
                    AS solar_generation_kwh,

                won.capacity_kw
                    AS wind_onshore_capacity_kw,

                won.volume_kwh
                    AS wind_onshore_generation_kwh,

                woff.capacity_kw
                    AS wind_offshore_capacity_kw,

                woff.volume_kwh
                    AS wind_offshore_generation_kwh,

                p.wholesale_price_eur_mwh

            FROM electricity_demand d

            LEFT JOIN solar_generation s
                ON datetime(d.interval_start_utc)
                 = datetime(s.valid_from_utc)

            LEFT JOIN wind_onshore_generation won
                ON datetime(d.interval_start_utc)
                 = datetime(won.valid_from_utc)

            LEFT JOIN wind_offshore_generation woff
                ON datetime(d.interval_start_utc)
                 = datetime(woff.valid_from_utc)

            LEFT JOIN wholesale_prices p
                ON datetime(d.interval_start_utc)
                 = datetime(p.interval_start_utc)
        """)

        # Validate the resulting view.
        total = connection.execute(
            "SELECT COUNT(*) FROM hourly_energy_model"
        ).fetchone()[0]

        unique_hours = connection.execute(
            """
            SELECT COUNT(DISTINCT interval_start_utc)
            FROM hourly_energy_model
            """
        ).fetchone()[0]

        missing_prices = connection.execute(
            """
            SELECT COUNT(*)
            FROM hourly_energy_model
            WHERE wholesale_price_eur_mwh IS NULL
            """
        ).fetchone()[0]

        print("\nANALYTICAL MODEL VALIDATION")
        print("=" * 55)

        print(f"Total records: {total}")
        print(f"Distinct hours: {unique_hours}")
        print(f"Missing wholesale prices: {missing_prices}")

        if (
            total != EXPECTED_HOURS
            or unique_hours != EXPECTED_HOURS
        ):
            raise RuntimeError(
                "Hourly model does not contain "
                "exactly 720 unique hourly records."
            )

        print("\nHourly energy model created successfully!")

        print("\nSAMPLE RECORDS")
        print("=" * 55)

        rows = connection.execute("""
            SELECT
                interval_start_utc,
                electricity_demand_mw,
                solar_generation_kwh,
                wind_onshore_generation_kwh,
                wind_offshore_generation_kwh,
                wholesale_price_eur_mwh
            FROM hourly_energy_model
            ORDER BY interval_start_utc
            LIMIT 5
        """).fetchall()

        for row in rows:
            print(row)


if __name__ == "__main__":
    create_analytical_model()
