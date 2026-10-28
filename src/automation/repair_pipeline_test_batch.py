"""Repair an unprocessed INNEVA.E synthetic pipeline test candidate.

Only edits the designated incoming CSV, after checking that it has the
expected 24-hour shape. Never touches production or development datasets.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path.home() / "Documents" / "Projects" / "INNEVAE"
CANDIDATE = ROOT / "data" / "refresh" / "incoming" / "pipeline_test_20261003.csv"
DEVELOPMENT = ROOT / "data" / "staging" / "energy_intelligence_hourly_development.csv"
PRODUCTION = ROOT / "data" / "forecasting" / "energy_intelligence_hourly.csv"
EXPECTED_PRODUCTION_SHA = "5b1c051071a497493a37121420c7ee5944814362464c394bc4082f306653684e"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not CANDIDATE.is_file() or CANDIDATE.is_symlink():
        raise RuntimeError(f"Missing or symlinked incoming test batch: {CANDIDATE}")
    if not DEVELOPMENT.is_file() or not PRODUCTION.is_file():
        raise RuntimeError("Development or production dataset is missing")
    prod_before = sha256(PRODUCTION)
    dev_before = sha256(DEVELOPMENT)
    if prod_before != EXPECTED_PRODUCTION_SHA:
        raise RuntimeError("Production checksum mismatch; refusing repair")

    df = pd.read_csv(CANDIDATE)
    if len(df) != 24:
        raise ValueError(f"Expected exactly 24 candidate rows; got {len(df)}")
    required = {"hour_start_utc", "hour_end_utc", "hour_of_day", "day_of_week", "month", "is_weekend"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns: {sorted(required - set(df.columns))}")

    starts = pd.to_datetime(df["hour_start_utc"], utc=True, format="mixed", errors="raise")
    expected = pd.date_range("2026-10-03T00:00:00Z", periods=24, freq="h")
    if not pd.DatetimeIndex(starts).equals(expected):
        raise ValueError("Candidate start hours are not exactly October 3, 2026 UTC")
    dev_last = pd.to_datetime(pd.read_csv(DEVELOPMENT, usecols=["hour_start_utc"])["hour_start_utc"].iloc[-1], utc=True)
    if dev_last + pd.Timedelta(hours=1) != expected[0]:
        raise ValueError(f"Candidate does not immediately follow development dataset: {dev_last}")

    ends = starts + pd.Timedelta(hours=1)
    df["hour_start_utc"] = starts.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    df["hour_end_utc"] = ends.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    df["hour_of_day"] = starts.dt.hour
    df["day_of_week"] = starts.dt.dayofweek
    df["month"] = starts.dt.month
    df["is_weekend"] = starts.dt.dayofweek >= 5

    if not ((pd.to_datetime(df["hour_end_utc"], utc=True) - pd.to_datetime(df["hour_start_utc"], utc=True)) == pd.Timedelta(hours=1)).all():
        raise RuntimeError("Hour interval verification failed")
    # Ensure the candidate hasn't changed while being inspected.
    original_sha = sha256(CANDIDATE)
    fd, temporary_name = tempfile.mkstemp(prefix=".pipeline-test-repair-", suffix=".csv", dir=CANDIDATE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            df.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256(CANDIDATE) != original_sha:
            raise RuntimeError("Candidate changed during repair")
        if sha256(PRODUCTION) != prod_before or sha256(DEVELOPMENT) != dev_before:
            raise RuntimeError("Source dataset changed during repair")
        os.replace(temporary_name, CANDIDATE)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    print(json.dumps({
        "status": "REPAIRED",
        "candidate_path": str(CANDIDATE),
        "rows": len(df),
        "first_hour_utc": df["hour_start_utc"].iloc[0],
        "last_hour_end_utc": df["hour_end_utc"].iloc[-1],
        "day_of_week": int(df["day_of_week"].iloc[0]),
        "is_weekend": bool(df["is_weekend"].iloc[0]),
        "production_unchanged": sha256(PRODUCTION) == prod_before,
        "development_unchanged": sha256(DEVELOPMENT) == dev_before,
    }, indent=2))


if __name__ == "__main__":
    main()
