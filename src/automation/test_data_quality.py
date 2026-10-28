
"""
INNEVA.E — Data Quality Regression Tests

Checkpoint 20.5A

Tests:
1. Baseline known warnings
2. Duplicate hourly timestamp
3. Missing hourly observation
4. MW/MWh inconsistency
5. Missingness flag inconsistency
6. Incorrect derived calendar hour
7. Mixed-format UTC timestamps
8. Invalid timestamp rejection

All tests use temporary CSV files.
Production and development datasets are never modified.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT / "src" / "automation"),
)

from data_quality_monitor import analyze


SOURCE = (
    ROOT
    / "data"
    / "forecasting"
    / "energy_intelligence_hourly.csv"
)


def baseline(df: pd.DataFrame) -> pd.DataFrame:
    return df


def duplicate_hour(df: pd.DataFrame) -> pd.DataFrame:
    df.loc[1, "hour_start_utc"] = df.loc[
        0, "hour_start_utc"
    ]
    return df


def missing_hour(df: pd.DataFrame) -> pd.DataFrame:
    # Critical fix:
    # Return the modified DataFrame so the test
    # actually removes the second observation.
    return df.drop(index=1).reset_index(drop=True)


def mw_mwh_mismatch(df: pd.DataFrame) -> pd.DataFrame:
    df.loc[0, "actual_load_mwh"] = (
        float(df.loc[0, "actual_load_mwh"]) + 100
    )
    return df


def missing_flag_mismatch(
    df: pd.DataFrame,
) -> pd.DataFrame:
    df.loc[0, "actual_load_missing"] = True
    return df


def wrong_calendar_hour(
    df: pd.DataFrame,
) -> pd.DataFrame:
    df.loc[0, "hour_of_day"] = (
        int(df.loc[0, "hour_of_day"]) + 1
    ) % 24
    return df


def mixed_timestamp_formats(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert one valid timestamp pair to ISO T format
    while retaining the historical format elsewhere.
    """
    for column in ("hour_start_utc", "hour_end_utc"):
        timestamp = pd.to_datetime(
            df.loc[1, column],
            utc=True,
        )
        df.loc[1, column] = timestamp.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )

    return df


def invalid_timestamp(
    df: pd.DataFrame,
) -> pd.DataFrame:
    df.loc[1, "hour_start_utc"] = "not-a-timestamp"
    return df


TESTS = [
    (
        "baseline_known_warnings",
        baseline,
        "WARNING",
        None,
    ),
    (
        "duplicate_hour",
        duplicate_hour,
        "FAIL",
        "duplicate_hours",
    ),
    (
        "missing_hour",
        missing_hour,
        "FAIL",
        "missing_hours",
    ),
    (
        "mw_mwh_mismatch",
        mw_mwh_mismatch,
        "FAIL",
        "mw_mwh_mismatch_actual_load",
    ),
    (
        "missing_flag_mismatch",
        missing_flag_mismatch,
        "FAIL",
        "flag_mismatch_actual_load_mw",
    ),
    (
        "wrong_calendar_hour",
        wrong_calendar_hour,
        "FAIL",
        "derived_mismatch_hour_of_day",
    ),
    (
        "mixed_timestamp_formats",
        mixed_timestamp_formats,
        "WARNING",
        None,
    ),
    (
        "invalid_timestamp",
        invalid_timestamp,
        "FAIL",
        "invalid_timestamp_hour_start_utc",
    ),
]


def run_tests() -> int:
    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"Production dataset not found: {SOURCE}"
        )

    original = pd.read_csv(SOURCE)

    failures = 0

    with tempfile.TemporaryDirectory(
        prefix="innevae_quality_regression_"
    ) as temporary_directory:

        temp = Path(temporary_directory)

        for (
            name,
            mutation,
            expected_status,
            expected_check,
        ) in TESTS:

            df = original.copy(deep=True)

            # Always use the returned DataFrame.
            # This supports both in-place edits
            # and operations such as drop().
            df = mutation(df)

            test_path = temp / f"{name}.csv"

            df.to_csv(
                test_path,
                index=False,
            )

            try:
                result = analyze(
                    test_path,
                    source_kind="synthetic",
                )

                failed_checks = {
                    issue["check"]
                    for issue in result["issues"]
                    if issue["severity"] == "FAIL"
                }

                correct_status = (
                    result["status"] == expected_status
                )

                correct_check = (
                    expected_check is None
                    or expected_check in failed_checks
                )

                passed = (
                    correct_status and correct_check
                )

                details = (
                    f"status={result['status']}, "
                    f"fails={result['counts']['fail']}, "
                    f"warnings={result['counts']['warning']}"
                )

            except Exception as error:
                passed = False
                details = (
                    f"{type(error).__name__}: {error}"
                )

            print(
                f"{'PASS' if passed else 'FAIL'} "
                f"| {name} | {details}"
            )

            if not passed:
                failures += 1

    total = len(TESTS)
    passed_count = total - failures

    print(
        f"\nRESULT: {passed_count}/{total} "
        "tests passed"
    )

    print(
        "DATASETS: Production and development "
        "files were never written by this script."
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
