
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ============================================================
# INNEVA.E AI ENERGY INTELLIGENCE PLATFORM
# DATABASE QUALITY VALIDATION - VERSION 2
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "database_quality_report.txt"
)

EXPECTED_COUNTS = {
    "electricity_demand": 720,
    "solar_generation": 720,
    "wind_onshore_generation": 720,
    "wind_offshore_generation": 720,
    "weather_observations": 34560,
    "wholesale_prices": 718,
    "grid_capacity": 602,
}

TIME_COLUMNS = {
    "electricity_demand": "interval_start_utc",
    "solar_generation": "valid_from_utc",
    "wind_onshore_generation": "valid_from_utc",
    "wind_offshore_generation": "valid_from_utc",
    "weather_observations": "interval_start_utc",
    "wholesale_prices": "interval_start_utc",
}

# Source fields documented as UTC, despite lacking
# an explicit timezone suffix in their stored strings.
NAIVE_UTC_TABLES = {
    "electricity_demand",
    "solar_generation",
    "wind_onshore_generation",
    "wind_offshore_generation",
}

CANDIDATE_KEYS = {
    "electricity_demand": [
        "interval_start_utc", "area"
    ],
    "solar_generation": [
        "valid_from_utc", "point", "type"
    ],
    "wind_onshore_generation": [
        "valid_from_utc", "point", "type"
    ],
    "wind_offshore_generation": [
        "valid_from_utc", "location",
        "generation_type"
    ],
    "weather_observations": [
        "interval_start_utc", "station_id"
    ],
    "wholesale_prices": [
        "interval_start_utc", "iso3_code"
    ],
}

NONNEGATIVE_COLUMNS = {
    "electricity_demand": [
        "actual_total_load_mw",
        "day_ahead_total_load_forecast_mw",
    ],
    "solar_generation": [
        "capacity_kw", "volume_kwh"
    ],
    "wind_onshore_generation": [
        "capacity_kw", "volume_kwh"
    ],
    "wind_offshore_generation": [
        "capacity_kw", "volume_kwh"
    ],
    "weather_observations": [
        "relative_humidity_pct",
        "global_radiation_j_cm2",
    ],
}

PERIOD_START = datetime(
    2026, 9, 1, tzinfo=timezone.utc
)

PERIOD_END = datetime(
    2026, 10, 1, tzinfo=timezone.utc
)

EXPECTED_HOURS = {
    PERIOD_START + timedelta(hours=hour)
    for hour in range(720)
}


def quote_identifier(value):
    """Quote a SQLite table or column name."""
    return '"' + value.replace('"', '""') + '"'


def parse_utc(value, allow_naive_utc=False):
    """
    Parse ISO timestamps and normalize to UTC.

    Naive timestamps are accepted only for tables
    explicitly documented as containing UTC values.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing timestamp")

    parsed = datetime.fromisoformat(
        value.strip().replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:

        if not allow_naive_utc:
            raise ValueError(
                f"Timezone missing: {value}"
            )

        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(timezone.utc)


def validate_database():

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report_lines = []
    errors = []
    warnings = []
    total_records = 0

    def log(message=""):
        print(message)
        report_lines.append(message)

    log("=" * 65)
    log("INNEVA.E DATABASE QUALITY REPORT")
    log("=" * 65)

    log(
        "Validation date: "
        + datetime.now().isoformat(
            timespec="seconds"
        )
    )

    log(
        "Timestamp policy: naive timestamps in four "
        "designated source tables are interpreted as UTC."
    )

    with sqlite3.connect(DATABASE_PATH) as connection:

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        log(f"\nSQLite integrity: {integrity}")

        if integrity != "ok":
            errors.append(
                f"Database integrity failure: {integrity}"
            )

        for table, expected_count in EXPECTED_COUNTS.items():

            log("\n" + "-" * 65)
            log(f"TABLE: {table}")
            log("-" * 65)

            table_q = quote_identifier(table)

            schema = connection.execute(
                f"PRAGMA table_info({table_q})"
            ).fetchall()

            if not schema:
                errors.append(
                    f"{table}: table is missing"
                )
                log("ERROR: Table is missing")
                continue

            columns = {
                row[1]: row[2].upper()
                for row in schema
            }

            count = connection.execute(
                f"SELECT COUNT(*) FROM {table_q}"
            ).fetchone()[0]

            total_records += count

            log(f"Records: {count:,}")
            log(f"Expected: {expected_count:,}")

            if count != expected_count:
                errors.append(
                    f"{table}: expected {expected_count}, "
                    f"found {count}"
                )

            # --------------------------------------------
            # COMPLETENESS
            # --------------------------------------------

            log("\nMissing values:")

            missing_found = False

            for column in columns:

                column_q = quote_identifier(column)

                missing = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {table_q}
                    WHERE {column_q} IS NULL
                       OR TRIM(
                           CAST({column_q} AS TEXT)
                       ) = ''
                    """
                ).fetchone()[0]

                if missing:
                    missing_found = True

                    percentage = (
                        100 * missing / count
                        if count else 0
                    )

                    log(
                        f"  {column}: {missing:,} "
                        f"({percentage:.1f}%)"
                    )

            if not missing_found:
                log("  No missing values")

            # --------------------------------------------
            # UNIQUENESS
            # --------------------------------------------

            if table in CANDIDATE_KEYS:

                keys = CANDIDATE_KEYS[table]

                group_columns = ", ".join(
                    quote_identifier(key)
                    for key in keys
                )

                duplicates = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM (
                        SELECT {group_columns}
                        FROM {table_q}
                        GROUP BY {group_columns}
                        HAVING COUNT(*) > 1
                    )
                    """
                ).fetchone()[0]

                log(
                    "\nDuplicate candidate-key groups: "
                    f"{duplicates}"
                )

                if duplicates:
                    warnings.append(
                        f"{table}: {duplicates} "
                        "duplicate candidate-key groups"
                    )

            # --------------------------------------------
            # NUMERIC VALIDITY
            # --------------------------------------------

            invalid_numeric = 0

            for column, declared_type in columns.items():

                if declared_type not in (
                    "REAL", "INTEGER"
                ):
                    continue

                column_q = quote_identifier(column)

                invalid = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {table_q}
                    WHERE {column_q} IS NOT NULL
                      AND typeof({column_q})
                          NOT IN ('integer', 'real')
                    """
                ).fetchone()[0]

                invalid_numeric += invalid

                if invalid:
                    errors.append(
                        f"{table}.{column}: "
                        f"{invalid} nonnumeric values"
                    )

            log(
                f"Invalid numeric values: "
                f"{invalid_numeric}"
            )

            # --------------------------------------------
            # NONNEGATIVE VALUES
            # --------------------------------------------

            for column in NONNEGATIVE_COLUMNS.get(
                table, []
            ):

                if column not in columns:
                    errors.append(
                        f"{table}: missing column {column}"
                    )
                    continue

                column_q = quote_identifier(column)

                negatives = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {table_q}
                    WHERE {column_q} < 0
                    """
                ).fetchone()[0]

                if negatives:
                    warnings.append(
                        f"{table}.{column}: "
                        f"{negatives} negative values"
                    )

                    log(
                        f"Negative {column}: "
                        f"{negatives}"
                    )

            # --------------------------------------------
            # TIMESTAMP VALIDATION
            # --------------------------------------------

            if table in TIME_COLUMNS:

                time_column = TIME_COLUMNS[table]

                if time_column not in columns:
                    errors.append(
                        f"{table}: missing time column"
                    )
                    continue

                time_q = quote_identifier(time_column)

                timestamps = connection.execute(
                    f"""
                    SELECT DISTINCT {time_q}
                    FROM {table_q}
                    WHERE {time_q} IS NOT NULL
                    """
                ).fetchall()

                actual_hours = set()
                invalid_timestamps = 0
                off_hour_timestamps = 0

                allow_naive = (
                    table in NAIVE_UTC_TABLES
                )

                for (value,) in timestamps:

                    try:
                        parsed = parse_utc(
                            value,
                            allow_naive_utc=allow_naive
                        )

                        actual_hours.add(parsed)

                        if (
                            parsed.minute != 0
                            or parsed.second != 0
                            or parsed.microsecond != 0
                        ):
                            off_hour_timestamps += 1

                    except (ValueError, TypeError):
                        invalid_timestamps += 1

                missing_hours = sorted(
                    EXPECTED_HOURS - actual_hours
                )

                extra_hours = sorted(
                    actual_hours - EXPECTED_HOURS
                )

                log(
                    "\nDistinct timestamps: "
                    f"{len(actual_hours)}"
                )

                log(
                    "Missing September hours: "
                    f"{len(missing_hours)}"
                )

                log(
                    "Outside September: "
                    f"{len(extra_hours)}"
                )

                log(
                    "Invalid timestamps: "
                    f"{invalid_timestamps}"
                )

                log(
                    "Non-hour-aligned timestamps: "
                    f"{off_hour_timestamps}"
                )

                if missing_hours:
                    warnings.append(
                        f"{table}: "
                        f"{len(missing_hours)} missing hours"
                    )

                    for hour in missing_hours[:10]:
                        log(
                            "  Missing: "
                            + hour.strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            )
                        )

                if extra_hours:
                    warnings.append(
                        f"{table}: "
                        f"{len(extra_hours)} "
                        "outside-period timestamps"
                    )

                if invalid_timestamps:
                    errors.append(
                        f"{table}: "
                        f"{invalid_timestamps} "
                        "invalid timestamps"
                    )

                if off_hour_timestamps:
                    warnings.append(
                        f"{table}: "
                        f"{off_hour_timestamps} "
                        "off-hour timestamps"
                    )

        # --------------------------------------------
        # FINAL SUMMARY
        # --------------------------------------------

        log("\n" + "=" * 65)
        log("FINAL VALIDATION SUMMARY")
        log("=" * 65)

        log(f"Total records: {total_records:,}")
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
    validate_database()
