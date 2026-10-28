
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from math import isclose, isfinite

# ============================================================
# INNEVA.E - INTEGRATED MODEL QUALITY ASSURANCE
# CHECKPOINT 11.15
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "integrated_model_quality_report.txt"
)

EXPECTED_HOURS = 720
EXPECTED_MISSING_PRICES = 2

START_DATE = datetime(2026, 9, 1)

EXPECTED_TIMESTAMPS = {
    (START_DATE + timedelta(hours=i)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    for i in range(EXPECTED_HOURS)
}


def validate_integrated_model():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    errors = []
    warnings = []
    report_lines = []

    def log(message=""):
        print(message)
        report_lines.append(message)

    def check(condition, description):
        if condition:
            log(f"PASS: {description}")
        else:
            log(f"FAIL: {description}")
            errors.append(description)

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.row_factory = sqlite3.Row

        log("=" * 65)
        log("INNEVA.E - INTEGRATED MODEL QUALITY ASSURANCE")
        log("=" * 65)

        # ----------------------------------------------------
        # 1. MODEL STRUCTURE
        # ----------------------------------------------------

        log("\n1. MODEL STRUCTURE")
        log("-" * 65)

        rows = connection.execute("""
            SELECT *
            FROM integrated_energy_intelligence
            ORDER BY interval_start_utc
        """).fetchall()

        check(
            len(rows) == EXPECTED_HOURS,
            "Integrated model contains 720 records"
        )

        actual_timestamps = {
            row["interval_start_utc"]
            for row in rows
        }

        check(
            len(actual_timestamps) == len(rows),
            "No duplicate hourly timestamps"
        )

        check(
            actual_timestamps == EXPECTED_TIMESTAMPS,
            "Complete September 2026 hourly coverage"
        )

        # ----------------------------------------------------
        # 2. RENEWABLE GENERATION CALCULATIONS
        # ----------------------------------------------------

        log("\n2. RENEWABLE GENERATION CALCULATIONS")
        log("-" * 65)

        generation_errors = 0

        for row in rows:

            components = [
                row["solar_generation_avg_mw"],
                row["wind_onshore_generation_avg_mw"],
                row["wind_offshore_generation_avg_mw"],
            ]

            total = row[
                "total_renewable_generation_avg_mw"
            ]

            if any(
                value is None
                for value in components
            ) or total is None:
                generation_errors += 1
                continue

            expected_total = sum(components)

            if not isclose(
                total,
                expected_total,
                rel_tol=1e-9,
                abs_tol=1e-6
            ):
                generation_errors += 1

        check(
            generation_errors == 0,
            "Renewable generation components sum correctly"
        )

        # ----------------------------------------------------
        # 3. SOURCE CONSISTENCY
        # ----------------------------------------------------

        log("\n3. SOURCE CONSISTENCY")
        log("-" * 65)

        source_rows = connection.execute("""
            SELECT
                e.interval_start_utc,
                e.electricity_demand_mw,
                e.demand_forecast_mw,
                e.wholesale_price_eur_mwh,
                e.solar_generation_kwh,
                e.wind_onshore_generation_kwh,
                e.wind_offshore_generation_kwh,
                w.avg_air_temperature_c,
                w.avg_wind_speed_ms
            FROM hourly_energy_model e
            LEFT JOIN hourly_weather_summary w
                ON e.interval_start_utc = w.interval_start_utc
        """).fetchall()

        source_by_hour = {
            row["interval_start_utc"]: row
            for row in source_rows
        }

        def same_number(left, right):
            if left is None or right is None:
                return left is None and right is None

            return (
                isfinite(left)
                and isfinite(right)
                and isclose(
                    left,
                    right,
                    rel_tol=1e-9,
                    abs_tol=1e-6
                )
            )

        mismatches = 0

        for row in rows:

            source = source_by_hour.get(
                row["interval_start_utc"]
            )

            if source is None:
                mismatches += 1
                continue

            comparisons = [
                (
                    row["electricity_demand_mw"],
                    source["electricity_demand_mw"]
                ),
                (
                    row["demand_forecast_mw"],
                    source["demand_forecast_mw"]
                ),
                (
                    row["wholesale_price_eur_mwh"],
                    source["wholesale_price_eur_mwh"]
                ),
                (
                    row["avg_air_temperature_c"],
                    source["avg_air_temperature_c"]
                ),
                (
                    row["avg_wind_speed_ms"],
                    source["avg_wind_speed_ms"]
                ),
                (
                    row["solar_generation_avg_mw"],
                    (
                        source["solar_generation_kwh"] / 1000.0
                        if source["solar_generation_kwh"] is not None
                        else None
                    )
                ),
                (
                    row["wind_onshore_generation_avg_mw"],
                    (
                        source["wind_onshore_generation_kwh"] / 1000.0
                        if source["wind_onshore_generation_kwh"] is not None
                        else None
                    )
                ),
                (
                    row["wind_offshore_generation_avg_mw"],
                    (
                        source["wind_offshore_generation_kwh"] / 1000.0
                        if source["wind_offshore_generation_kwh"] is not None
                        else None
                    )
                ),
            ]

            if any(
                not same_number(left, right)
                for left, right in comparisons
            ):
                mismatches += 1

        check(
            len(source_by_hour) == EXPECTED_HOURS,
            "Source model contains 720 unique hours"
        )

        check(
            mismatches == 0,
            "Integrated values match their source models"
        )

        # ----------------------------------------------------
        # 4. WEATHER PLAUSIBILITY
        # ----------------------------------------------------

        log("\n4. WEATHER PLAUSIBILITY")
        log("-" * 65)

        weather_rules = {
            "avg_relative_humidity_pct": (0, 100),
            "avg_cloud_cover_oktas": (0, 8),
            "avg_wind_speed_ms": (0, 100),
            "avg_air_temperature_c": (-50, 60),
            "avg_solar_radiation_j_cm2": (0, 1000),
            "avg_precipitation_mm": (0, 500),
        }

        for column, (minimum, maximum) in weather_rules.items():

            invalid = 0
            missing = 0

            for row in rows:

                value = row[column]

                if value is None:
                    missing += 1
                    continue

                if (
                    not isfinite(value)
                    or value < minimum
                    or value > maximum
                ):
                    invalid += 1

            check(
                invalid == 0,
                f"{column} within plausibility range"
            )

            if missing:
                warnings.append(
                    f"{column}: {missing} missing hours"
                )

        # ----------------------------------------------------
        # 5. WEATHER STATION COVERAGE
        # ----------------------------------------------------

        log("\n5. WEATHER STATION COVERAGE")
        log("-" * 65)

        station_columns = [
            "wind_reporting_stations",
            "temperature_reporting_stations",
            "solar_reporting_stations",
            "humidity_reporting_stations",
            "precipitation_reporting_stations",
            "cloud_reporting_stations",
        ]

        check(
            all(
                row["total_stations"] == 48
                for row in rows
            ),
            "48 weather station records per hour"
        )

        for column in station_columns:

            valid = all(
                row[column] is not None
                and 0 <= row[column] <= 48
                for row in rows
            )

            check(
                valid,
                f"{column} between 0 and 48"
            )

        # ----------------------------------------------------
        # 6. MISSING WHOLESALE PRICES
        # ----------------------------------------------------

        log("\n6. WHOLESALE PRICE COMPLETENESS")
        log("-" * 65)

        missing_prices = [
            row["interval_start_utc"]
            for row in rows
            if row["wholesale_price_eur_mwh"] is None
        ]

        log(
            f"Missing wholesale prices: "
            f"{len(missing_prices)}"
        )

        for timestamp in missing_prices:
            log(f"  Missing: {timestamp}")

        check(
            len(missing_prices)
            == EXPECTED_MISSING_PRICES,
            "Expected two missing wholesale prices"
        )

        if missing_prices:
            warnings.append(
                f"{len(missing_prices)} missing "
                "wholesale price observations"
            )

        # ----------------------------------------------------
        # 7. FINAL REPORT
        # ----------------------------------------------------

        log("\n" + "=" * 65)
        log("FINAL QUALITY ASSURANCE SUMMARY")
        log("=" * 65)

        log(f"Total records: {len(rows)}")
        log(f"Errors: {len(errors)}")
        log(f"Warnings: {len(warnings)}")

        if errors:
            log("\nERRORS:")
            for error in errors:
                log(f" - {error}")

        if warnings:
            log("\nWARNINGS:")
            for warning in warnings:
                log(f" - {warning}")

        if errors:
            log("\nRESULT: FAILED")
        elif warnings:
            log("\nRESULT: PASSED WITH WARNINGS")
        else:
            log("\nRESULT: PASSED")

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8"
    )

    print(f"\nReport saved to: {REPORT_PATH}")


if __name__ == "__main__":
    validate_integrated_model()
