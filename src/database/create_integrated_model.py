
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - INTEGRATED ENERGY INTELLIGENCE MODEL
# CHECKPOINT 11.14
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

VIEW_NAME = "integrated_energy_intelligence"

EXPECTED_HOURS = 720


def create_integrated_model():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    with sqlite3.connect(DATABASE_PATH) as connection:

        print("=" * 65)
        print("INNEVA.E - INTEGRATED ENERGY INTELLIGENCE")
        print("=" * 65)

        # ----------------------------------------------------
        # 1. VERIFY DEPENDENT VIEWS
        # ----------------------------------------------------

        required_views = [
            "hourly_energy_model",
            "hourly_weather_summary",
        ]

        for view in required_views:

            exists = connection.execute(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'view'
                  AND name = ?
                """,
                (view,)
            ).fetchone()[0]

            if not exists:
                raise RuntimeError(
                    f"Required view not found: {view}"
                )

            print(f"Verified: {view}")

        # ----------------------------------------------------
        # 2. CREATE INTEGRATED VIEW
        # ----------------------------------------------------

        connection.execute(
            f'DROP VIEW IF EXISTS "{VIEW_NAME}"'
        )

        connection.execute("""
            CREATE VIEW integrated_energy_intelligence AS

            SELECT

                e.interval_start_utc,
                e.area,

                -- ELECTRICITY DEMAND

                e.electricity_demand_mw,
                e.demand_forecast_mw,

                -- RENEWABLE GENERATION
                -- kWh per hour converted to average MW

                e.solar_generation_kwh / 1000.0
                    AS solar_generation_avg_mw,

                e.wind_onshore_generation_kwh / 1000.0
                    AS wind_onshore_generation_avg_mw,

                e.wind_offshore_generation_kwh / 1000.0
                    AS wind_offshore_generation_avg_mw,

                -- TOTAL RENEWABLE GENERATION

                (
                    e.solar_generation_kwh
                    + e.wind_onshore_generation_kwh
                    + e.wind_offshore_generation_kwh
                ) / 1000.0
                    AS total_renewable_generation_avg_mw,

                -- WHOLESALE ELECTRICITY PRICES

                e.wholesale_price_eur_mwh,

                -- WEATHER CONDITIONS

                w.avg_wind_speed_ms,
                w.avg_air_temperature_c,
                w.avg_solar_radiation_j_cm2,
                w.avg_relative_humidity_pct,
                w.avg_precipitation_mm,
                w.avg_cloud_cover_oktas,

                -- WEATHER REPORTING COVERAGE

                w.total_stations,
                w.wind_reporting_stations,
                w.temperature_reporting_stations,
                w.solar_reporting_stations,
                w.humidity_reporting_stations,
                w.precipitation_reporting_stations,
                w.cloud_reporting_stations

            FROM hourly_energy_model e

            LEFT JOIN hourly_weather_summary w
                ON e.interval_start_utc
                 = w.interval_start_utc
        """)

        # ----------------------------------------------------
        # 3. VALIDATE MODEL
        # ----------------------------------------------------

        total = connection.execute("""
            SELECT COUNT(*)
            FROM integrated_energy_intelligence
        """).fetchone()[0]

        unique_hours = connection.execute("""
            SELECT COUNT(DISTINCT interval_start_utc)
            FROM integrated_energy_intelligence
        """).fetchone()[0]

        missing_weather = connection.execute("""
            SELECT COUNT(*)
            FROM integrated_energy_intelligence
            WHERE total_stations IS NULL
        """).fetchone()[0]

        missing_prices = connection.execute("""
            SELECT COUNT(*)
            FROM integrated_energy_intelligence
            WHERE wholesale_price_eur_mwh IS NULL
        """).fetchone()[0]

        print("\nMODEL VALIDATION")
        print("-" * 65)

        print(f"Total records: {total}")
        print(f"Distinct hours: {unique_hours}")
        print(f"Missing weather hours: {missing_weather}")
        print(f"Missing wholesale prices: {missing_prices}")

        if total != EXPECTED_HOURS:
            raise RuntimeError(
                f"Expected {EXPECTED_HOURS} records, "
                f"found {total}."
            )

        if unique_hours != EXPECTED_HOURS:
            raise RuntimeError(
                "Duplicate or missing hourly timestamps."
            )

        if missing_weather:
            raise RuntimeError(
                "Weather data is missing for "
                f"{missing_weather} hours."
            )

        # ----------------------------------------------------
        # 4. SAMPLE RECORDS
        # ----------------------------------------------------

        print("\nSAMPLE RECORDS")
        print("-" * 65)

        rows = connection.execute("""
            SELECT
                interval_start_utc,
                ROUND(electricity_demand_mw, 2),
                ROUND(total_renewable_generation_avg_mw, 2),
                ROUND(wholesale_price_eur_mwh, 2),
                ROUND(avg_air_temperature_c, 2),
                ROUND(avg_wind_speed_ms, 2)
            FROM integrated_energy_intelligence
            ORDER BY interval_start_utc
            LIMIT 5
        """).fetchall()

        for row in rows:
            print(row)

        print(
            "\nIntegrated energy intelligence "
            "model created successfully!"
        )


if __name__ == "__main__":
    create_integrated_model()
