
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - HOURLY WEATHER MODEL
# CHECKPOINT 11.15 - TRACE PRECIPITATION CORRECTION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

VIEW_NAME = "hourly_weather_summary"
EXPECTED_HOURS = 720
EXPECTED_STATIONS = 48


def create_weather_model():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    with sqlite3.connect(DATABASE_PATH) as connection:

        print("=" * 65)
        print("INNEVA.E - HOURLY WEATHER MODEL")
        print("=" * 65)

        duplicates = connection.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT interval_start_utc, station_id
                FROM weather_observations
                GROUP BY interval_start_utc, station_id
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        if duplicates:
            raise ValueError(
                f"Found {duplicates} duplicate station-hour records."
            )

        invalid_precipitation = connection.execute("""
            SELECT COUNT(*)
            FROM weather_observations
            WHERE precipitation_amount_0_1_mm < 0
              AND precipitation_amount_0_1_mm != -1
        """).fetchone()[0]

        if invalid_precipitation:
            raise ValueError(
                f"Found {invalid_precipitation} unexpected "
                "negative precipitation codes."
            )

        # KNMI precipitation convention:
        # NULL = no measurement
        # -1   = trace precipitation (<0.05 mm)
        # 0    = zero recorded precipitation
        # >0   = amount in tenths of a millimeter
        #
        # Approximation for numerical averages:
        # trace precipitation -> 0.0 mm
        #
        # Trace counts are retained separately.

        connection.execute(
            f'DROP VIEW IF EXISTS "{VIEW_NAME}"'
        )

        connection.execute("""
            CREATE VIEW hourly_weather_summary AS

            SELECT
                datetime(interval_start_utc)
                    AS interval_start_utc,

                COUNT(DISTINCT station_id)
                    AS total_stations,

                AVG(hourly_mean_wind_speed_0_1_ms) / 10.0
                    AS avg_wind_speed_ms,

                COUNT(hourly_mean_wind_speed_0_1_ms)
                    AS wind_reporting_stations,

                AVG(air_temperature_0_1_c) / 10.0
                    AS avg_air_temperature_c,

                COUNT(air_temperature_0_1_c)
                    AS temperature_reporting_stations,

                AVG(global_radiation_j_cm2)
                    AS avg_solar_radiation_j_cm2,

                COUNT(global_radiation_j_cm2)
                    AS solar_reporting_stations,

                AVG(relative_humidity_pct)
                    AS avg_relative_humidity_pct,

                COUNT(relative_humidity_pct)
                    AS humidity_reporting_stations,

                AVG(
                    CASE
                        WHEN precipitation_amount_0_1_mm = -1
                            THEN 0.0
                        ELSE precipitation_amount_0_1_mm / 10.0
                    END
                ) AS avg_precipitation_mm,

                COUNT(precipitation_amount_0_1_mm)
                    AS precipitation_reporting_stations,

                SUM(
                    CASE
                        WHEN precipitation_amount_0_1_mm = -1
                            THEN 1
                        ELSE 0
                    END
                ) AS precipitation_trace_stations,

                AVG(
                    CASE
                        WHEN cloud_cover_oktas BETWEEN 0 AND 8
                            THEN cloud_cover_oktas
                        ELSE NULL
                    END
                ) AS avg_cloud_cover_oktas,

                COUNT(
                    CASE
                        WHEN cloud_cover_oktas BETWEEN 0 AND 8
                            THEN cloud_cover_oktas
                        ELSE NULL
                    END
                ) AS cloud_reporting_stations

            FROM weather_observations
            GROUP BY datetime(interval_start_utc)
        """)

        total, unique_hours = connection.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT interval_start_utc)
            FROM hourly_weather_summary
        """).fetchone()

        minimum_stations, maximum_stations = connection.execute("""
            SELECT MIN(total_stations), MAX(total_stations)
            FROM hourly_weather_summary
        """).fetchone()

        negative_averages = connection.execute("""
            SELECT COUNT(*)
            FROM hourly_weather_summary
            WHERE avg_precipitation_mm < 0
        """).fetchone()[0]

        trace_observations = connection.execute("""
            SELECT SUM(precipitation_trace_stations)
            FROM hourly_weather_summary
        """).fetchone()[0]

        print("\nMODEL VALIDATION")
        print("-" * 65)
        print(f"Total hourly records: {total}")
        print(f"Distinct hours: {unique_hours}")
        print(f"Minimum stations per hour: {minimum_stations}")
        print(f"Maximum stations per hour: {maximum_stations}")
        print(f"Negative precipitation averages: {negative_averages}")
        print(f"Trace precipitation observations: {trace_observations}")

        if total != EXPECTED_HOURS or unique_hours != EXPECTED_HOURS:
            raise RuntimeError("Hourly coverage validation failed.")

        if (
            minimum_stations != EXPECTED_STATIONS
            or maximum_stations != EXPECTED_STATIONS
        ):
            raise RuntimeError("Station coverage validation failed.")

        if negative_averages:
            raise RuntimeError(
                "Negative precipitation averages remain."
            )

        print("\nSAMPLE PRECIPITATION RECORDS")
        print("-" * 65)

        rows = connection.execute("""
            SELECT
                interval_start_utc,
                ROUND(avg_precipitation_mm, 4),
                precipitation_reporting_stations,
                precipitation_trace_stations
            FROM hourly_weather_summary
            ORDER BY interval_start_utc
            LIMIT 5
        """).fetchall()

        for row in rows:
            print(row)

        print("\nHourly weather model updated successfully!")


if __name__ == "__main__":
    create_weather_model()
