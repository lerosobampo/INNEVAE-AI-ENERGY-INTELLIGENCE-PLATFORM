
import sqlite3
from pathlib import Path

# ============================================================
# INNEVA.E - WEATHER STATION COVERAGE ANALYSIS
# CHECKPOINT 11.12
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "weather_station_coverage_report.txt"
)

EXPECTED_HOURS = 720

WEATHER_VARIABLES = {
    "wind_speed": "hourly_mean_wind_speed_0_1_ms",
    "air_temperature": "air_temperature_0_1_c",
    "solar_radiation": "global_radiation_j_cm2",
    "relative_humidity": "relative_humidity_pct",
    "precipitation": "precipitation_amount_0_1_mm",
    "cloud_cover": "cloud_cover_oktas",
}


def analyze_weather_coverage():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report_lines = []

    def log(message=""):
        print(message)
        report_lines.append(message)

    with sqlite3.connect(DATABASE_PATH) as connection:

        log("=" * 75)
        log("INNEVA.E WEATHER STATION COVERAGE REPORT")
        log("=" * 75)

        station_count = connection.execute("""
            SELECT COUNT(DISTINCT station_id)
            FROM weather_observations
        """).fetchone()[0]

        total_records = connection.execute("""
            SELECT COUNT(*)
            FROM weather_observations
        """).fetchone()[0]

        log(f"\nWeather stations: {station_count}")
        log(f"Total observations: {total_records:,}")
        log(f"Expected observations per station: {EXPECTED_HOURS}")

        # ----------------------------------------------------
        # 1. STATION-LEVEL COVERAGE
        # ----------------------------------------------------

        log("\n" + "=" * 75)
        log("STATION-LEVEL COVERAGE")
        log("=" * 75)

        columns = [
            "station_id",
            "COUNT(*) AS total_hours",
        ]

        for alias, column in WEATHER_VARIABLES.items():
            columns.append(
                f'COUNT("{column}") AS "{alias}"'
            )

        query = f"""
            SELECT {", ".join(columns)}
            FROM weather_observations
            GROUP BY station_id
            ORDER BY station_id
        """

        cursor = connection.execute(query)

        headers = [item[0] for item in cursor.description]
        station_rows = cursor.fetchall()

        log("\n" + " | ".join(headers))
        log("-" * 100)

        for row in station_rows:
            log(" | ".join(str(value) for value in row))

        # ----------------------------------------------------
        # 2. VARIABLE AVAILABILITY
        # ----------------------------------------------------

        log("\n" + "=" * 75)
        log("VARIABLE AVAILABILITY")
        log("=" * 75)

        for alias, column in WEATHER_VARIABLES.items():

            available = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM weather_observations
                WHERE "{column}" IS NOT NULL
                """
            ).fetchone()[0]

            percentage = (
                100 * available / total_records
                if total_records else 0
            )

            complete_stations = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT station_id
                    FROM weather_observations
                    GROUP BY station_id
                    HAVING COUNT(*) = ?
                       AND COUNT("{column}") = ?
                )
                """,
                (EXPECTED_HOURS, EXPECTED_HOURS)
            ).fetchone()[0]

            log(
                f"{alias}: "
                f"{available:,}/{total_records:,} observations "
                f"({percentage:.1f}% available), "
                f"{complete_stations} fully covered stations"
            )

        # ----------------------------------------------------
        # 3. HOURLY AVAILABILITY
        # ----------------------------------------------------

        log("\n" + "=" * 75)
        log("HOURLY MEASUREMENT AVAILABILITY")
        log("=" * 75)

        for alias, column in WEATHER_VARIABLES.items():

            minimum, maximum, average = connection.execute(
                f"""
                SELECT
                    MIN(station_count),
                    MAX(station_count),
                    AVG(station_count)
                FROM (
                    SELECT
                        interval_start_utc,
                        COUNT("{column}") AS station_count
                    FROM weather_observations
                    GROUP BY interval_start_utc
                )
                """
            ).fetchone()

            log(
                f"{alias}: "
                f"min={minimum}, "
                f"max={maximum}, "
                f"avg={average:.1f} stations/hour"
            )

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8"
    )

    print(f"\nReport saved to: {REPORT_PATH}")


if __name__ == "__main__":
    analyze_weather_coverage()
