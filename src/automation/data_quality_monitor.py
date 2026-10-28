
"""
INNEVA.E — Energy Data Quality Monitor

Checkpoint 20.5A

Read-only validation of historical and synthetic energy datasets.

Features:
- Exact canonical schema validation
- Mixed-format UTC timestamp parsing
- Duplicate timestamp detection
- Missing hourly observation detection
- Hour duration validation
- Missingness flag consistency
- Physical plausibility checks
- MW/MWh consistency
- Derived calendar validation
- Station count validation
- Missing measurement warnings
- Historical/synthetic freshness reporting

This script never modifies source datasets.
"""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATASET = (
    ROOT
    / "data"
    / "forecasting"
    / "energy_intelligence_hourly.csv"
)


EXPECTED_COLUMNS = (
    "hour_start_utc",
    "hour_end_utc",
    "actual_load_mw",
    "actual_load_mwh",
    "actual_load_missing",
    "solar_mw",
    "solar_mwh",
    "solar_missing",
    "wind_onshore_mw",
    "wind_onshore_mwh",
    "wind_onshore_missing",
    "wind_offshore_mw",
    "wind_offshore_mwh",
    "wind_offshore_missing",
    "wholesale_price_eur_mwh",
    "price_missing",
    "station_count",
    "temperature_c",
    "wind_speed_ms",
    "solar_radiation_wm2",
    "cloud_cover_oktas",
    "relative_humidity_pct",
    "precipitation_mm",
    "sunshine_hours",
    "pressure_hpa",
    "temperature_c_station_count",
    "wind_speed_ms_station_count",
    "solar_radiation_wm2_station_count",
    "cloud_cover_oktas_station_count",
    "relative_humidity_pct_station_count",
    "precipitation_mm_station_count",
    "sunshine_hours_station_count",
    "pressure_hpa_station_count",
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
)


FLAGS = {
    "actual_load_missing": (
        "actual_load_mw",
        "actual_load_mwh",
    ),
    "solar_missing": (
        "solar_mw",
        "solar_mwh",
    ),
    "wind_onshore_missing": (
        "wind_onshore_mw",
        "wind_onshore_mwh",
    ),
    "wind_offshore_missing": (
        "wind_offshore_mw",
        "wind_offshore_mwh",
    ),
    "price_missing": (
        "wholesale_price_eur_mwh",
    ),
}


BOUNDS = {
    "actual_load_mw": (0, None),
    "solar_mw": (0, None),
    "wind_onshore_mw": (0, None),
    "wind_offshore_mw": (0, None),
    "wind_speed_ms": (0, None),
    "solar_radiation_wm2": (0, None),
    "cloud_cover_oktas": (0, 8),
    "relative_humidity_pct": (0, 100),
    "precipitation_mm": (0, None),
    "sunshine_hours": (0, 1),
    "pressure_hpa": (800, 1100),
    "temperature_c": (-80, 65),
}


def parse_utc_timestamps(values: pd.Series) -> pd.Series:
    """
    Parse valid mixed-format UTC timestamps.

    Supported examples:
        2026-10-01 23:00:00+00:00
        2026-10-02T00:00:00+00:00

    Invalid values become NaT.
    """

    return pd.to_datetime(
        values,
        utc=True,
        errors="coerce",
        format="mixed",
    )


def analyze(
    path: Path,
    source_kind: str = "historical",
) -> dict:
    """
    Validate a canonical energy CSV without modifying it.

    Returns a JSON-serializable quality report.
    """

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {path}"
        )

    df = pd.read_csv(path)

    issues = []

    def add_issue(
        severity: str,
        check: str,
        count: int,
        detail: str,
    ) -> None:

        count = int(count)

        if count <= 0:
            return

        issues.append(
            {
                "severity": severity,
                "check": check,
                "count": count,
                "detail": detail,
            }
        )

    # ==========================================
    # 1. SCHEMA
    # ==========================================

    if list(df.columns) != list(EXPECTED_COLUMNS):
        raise ValueError(
            "Dataset must contain the exact canonical "
            "37 columns in the expected order"
        )

    if df.empty:
        raise ValueError("Dataset is empty")

    # ==========================================
    # 2. TIMESTAMPS
    # ==========================================

    for column in (
        "hour_start_utc",
        "hour_end_utc",
    ):

        df[column] = parse_utc_timestamps(
            df[column]
        )

        add_issue(
            "FAIL",
            f"invalid_timestamp_{column}",
            df[column].isna().sum(),
            "Timestamp cannot be parsed",
        )

    starts = df["hour_start_utc"]
    ends = df["hour_end_utc"]

    valid_starts = starts.dropna()

    # Duplicate detection
    duplicates = valid_starts.duplicated(
        keep="first"
    )

    add_issue(
        "FAIL",
        "duplicate_hours",
        duplicates.sum(),
        "Duplicate UTC hour_start_utc values",
    )

    # Original row ordering
    unsorted = (
        not valid_starts.is_monotonic_increasing
    )

    add_issue(
        "FAIL",
        "unsorted_hours",
        int(unsorted),
        "Hours are not strictly ascending",
    )

    # ==========================================
    # 3. HOURLY CONTINUITY
    # ==========================================

    # This explicitly compares consecutive valid
    # timestamps. It detects missing hours even when
    # a row has been removed and the remaining rows
    # are otherwise sorted.

    sorted_starts = (
        valid_starts
        .sort_values()
        .reset_index(drop=True)
    )

    hourly_differences = sorted_starts.diff()

    gap_differences = hourly_differences[
        hourly_differences > pd.Timedelta(hours=1)
    ]

    missing_hour_count = int(
        sum(
            int(
                difference
                / pd.Timedelta(hours=1)
            ) - 1
            for difference in gap_differences
        )
    )

    add_issue(
        "FAIL",
        "missing_hours",
        missing_hour_count,
        "Missing UTC hourly timestamps "
        "within dataset range",
    )

    # Also detect intervals shorter than one hour.
    short_intervals = (
        hourly_differences.notna()
        & (
            hourly_differences
            < pd.Timedelta(hours=1)
        )
    )

    add_issue(
        "FAIL",
        "invalid_hour_spacing",
        short_intervals.sum(),
        "Consecutive timestamps must be "
        "separated by one hour",
    )

    # ==========================================
    # 4. HOURLY DURATION
    # ==========================================

    valid_duration = (
        starts.notna()
        & ends.notna()
    )

    durations = (
        ends[valid_duration]
        - starts[valid_duration]
    )

    invalid_durations = (
        durations != pd.Timedelta(hours=1)
    )

    add_issue(
        "FAIL",
        "invalid_hour_duration",
        invalid_durations.sum(),
        "Each observation must span exactly one hour",
    )

    # ==========================================
    # 5. MISSINGNESS FLAGS
    # ==========================================

    for flag, measurements in FLAGS.items():

        flag_values = (
            df[flag]
            .astype("string")
            .str.lower()
        )

        valid_flags = flag_values.isin(
            ["true", "false"]
        )

        add_issue(
            "FAIL",
            f"invalid_flag_{flag}",
            (~valid_flags).sum(),
            "Missingness flag must be true or false",
        )

        for measurement in measurements:

            mismatch = (
                valid_flags
                & (
                    df[measurement].isna()
                    != flag_values.eq("true")
                )
            )

            add_issue(
                "FAIL",
                f"flag_mismatch_{measurement}",
                mismatch.sum(),
                f"{flag} disagrees with null values",
            )

    # ==========================================
    # 6. PHYSICAL BOUNDS
    # ==========================================

    for column, (lower, upper) in BOUNDS.items():

        values = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        invalid_numeric = (
            df[column].notna()
            & values.isna()
        )

        add_issue(
            "FAIL",
            f"non_numeric_{column}",
            invalid_numeric.sum(),
            "Expected numeric measurement",
        )

        outside_bounds = pd.Series(
            False,
            index=df.index,
        )

        if lower is not None:
            outside_bounds |= values < lower

        if upper is not None:
            outside_bounds |= values > upper

        add_issue(
            "FAIL",
            f"out_of_bounds_{column}",
            outside_bounds.sum(),
            f"Plausibility bounds: {lower} to {upper}",
        )

    # ==========================================
    # 7. MW / MWH CONSISTENCY
    # ==========================================

    for measurement in (
        "actual_load",
        "solar",
        "wind_onshore",
        "wind_offshore",
    ):

        mw = pd.to_numeric(
            df[f"{measurement}_mw"],
            errors="coerce",
        )

        mwh = pd.to_numeric(
            df[f"{measurement}_mwh"],
            errors="coerce",
        )

        mismatch = (
            (mw - mwh).abs() > 0.02
        )

        add_issue(
            "FAIL",
            f"mw_mwh_mismatch_{measurement}",
            mismatch.sum(),
            "One-hour MW and MWh should agree "
            "within tolerance 0.02",
        )

    # ==========================================
    # 8. DERIVED CALENDAR FIELDS
    # ==========================================

    derived = {
        "hour_of_day": starts.dt.hour,
        "day_of_week": starts.dt.dayofweek,
        "month": starts.dt.month,
        "is_weekend": starts.dt.dayofweek >= 5,
    }

    for column, expected in derived.items():

        if column == "is_weekend":

            actual = (
                df[column]
                .astype("string")
                .str.lower()
            )

            expected_values = (
                expected
                .astype("string")
                .str.lower()
            )

        else:

            actual = pd.to_numeric(
                df[column],
                errors="coerce",
            )

            expected_values = expected

        mismatch = (
            starts.notna()
            & (actual != expected_values)
        )

        add_issue(
            "FAIL",
            f"derived_mismatch_{column}",
            mismatch.sum(),
            "Derived calendar value disagrees "
            "with UTC timestamp",
        )

    # ==========================================
    # 9. STATION COUNTS
    # ==========================================

    count_columns = [
        column
        for column in df.columns
        if column.endswith("_station_count")
    ]

    count_columns.append("station_count")

    for column in count_columns:

        values = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        invalid = (
            values.isna()
            | (values < 0)
            | (values % 1 != 0)
        )

        add_issue(
            "FAIL",
            f"invalid_count_{column}",
            invalid.sum(),
            "Station counts must be "
            "nonnegative integers",
        )

    # ==========================================
    # 10. MISSING MEASUREMENTS
    # ==========================================

    missing_values = {
        column: int(df[column].isna().sum())
        for column in df.columns
        if df[column].isna().any()
    }

    for column, count in missing_values.items():

        add_issue(
            "WARNING",
            f"missing_measurement_{column}",
            count,
            "Missing observations reported; "
            "do not impute automatically",
        )

    # ==========================================
    # 11. COVERAGE AND FRESHNESS
    # ==========================================

    first_hour = starts.min()
    last_hour = starts.max()

    if pd.notna(last_hour):

        age_hours = round(
            (
                pd.Timestamp.now(tz="UTC")
                - last_hour
            ).total_seconds() / 3600,
            2,
        )

    else:
        age_hours = None

    if (
        age_hours is not None
        and age_hours < 0
    ):

        add_issue(
            "WARNING",
            "future_timestamp",
            1,
            "Dataset contains future timestamps",
        )

    # ==========================================
    # 12. STATUS
    # ==========================================

    fail_count = sum(
        issue["severity"] == "FAIL"
        for issue in issues
    )

    warning_count = sum(
        issue["severity"] == "WARNING"
        for issue in issues
    )

    if fail_count:
        status = "FAIL"

    elif warning_count:
        status = "WARNING"

    else:
        status = "PASS"

    # ==========================================
    # 13. REPORT
    # ==========================================

    return {
        "status": status,
        "read_only": True,
        "source_kind": source_kind,
        "dataset": str(path.resolve()),
        "rows": len(df),
        "columns": len(df.columns),
        "first_hour_utc": (
            first_hour.isoformat()
            if pd.notna(first_hour)
            else None
        ),
        "last_hour_utc": (
            last_hour.isoformat()
            if pd.notna(last_hour)
            else None
        ),
        "age_of_last_observation_hours": (
            age_hours
        ),
        "freshness_policy": (
            "INFORMATIONAL_ONLY_FOR_HISTORICAL_OR_SYNTHETIC"
        ),
        "missing_values": missing_values,
        "counts": {
            "fail": fail_count,
            "warning": warning_count,
        },
        "issues": issues,
    }


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "INNEVA.E read-only "
            "energy data quality monitor"
        )
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
    )

    parser.add_argument(
        "--source-kind",
        choices=[
            "historical",
            "synthetic",
        ],
        default="historical",
    )

    args = parser.parse_args()

    try:

        report = analyze(
            args.dataset,
            source_kind=args.source_kind,
        )

        print(
            json.dumps(
                report,
                indent=2,
            )
        )

        return (
            2
            if report["status"] == "FAIL"
            else 0
        )

    except (
        ValueError,
        FileNotFoundError,
        pd.errors.ParserError,
    ) as error:

        print(
            f"QUALITY_CHECK_ERROR: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    raise SystemExit(main())
