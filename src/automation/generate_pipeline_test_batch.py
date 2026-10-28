"""INNEVA.E — Controlled synthetic pipeline test batch.

Creates a 24-hour development-only candidate using the latest 24 hourly
observations as a template. Does not modify production or development CSVs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT = ROOT / "data/staging/energy_intelligence_hourly_development.csv"
INCOMING = ROOT / "data/refresh/incoming"


def main() -> None:
    if not DEVELOPMENT.is_file():
        raise FileNotFoundError(DEVELOPMENT)

    history = pd.read_csv(DEVELOPMENT)
    if "hour_start_utc" not in history.columns:
        raise ValueError("Missing hour_start_utc column")

    # Development history contains both space-separated and T-separated ISO timestamps.
    history["hour_start_utc"] = pd.to_datetime(
        history["hour_start_utc"], utc=True, format="mixed", errors="raise"
    )
    history = history.sort_values("hour_start_utc").reset_index(drop=True)

    if history["hour_start_utc"].isna().any():
        raise ValueError("History contains missing timestamps")
    if history["hour_start_utc"].duplicated().any():
        raise ValueError("History contains duplicate timestamps")

    previous_day = history.tail(24).copy()
    if len(previous_day) != 24:
        raise ValueError("Insufficient historical observations")

    latest = previous_day["hour_start_utc"].iloc[-1]
    expected_previous = pd.date_range(end=latest, periods=24, freq="h")
    if not pd.DatetimeIndex(previous_day["hour_start_utc"]).equals(expected_previous):
        raise ValueError("Latest 24 historical hours are not continuous")

    candidate = previous_day.copy()
    candidate["hour_start_utc"] = candidate["hour_start_utc"] + pd.Timedelta(hours=24)
    expected_start = latest + pd.Timedelta(hours=1)
    if candidate["hour_start_utc"].iloc[0] != expected_start:
        raise ValueError("Candidate does not begin at the next UTC hour")

    # Preserve the exact original column order and encode UTC timestamps consistently.
    candidate = candidate[history.columns]
    candidate["hour_start_utc"] = candidate["hour_start_utc"].dt.strftime(
        "%Y-%m-%dT%H:%M:%S+00:00"
    )

    INCOMING.mkdir(parents=True, exist_ok=True)
    destination = INCOMING / f"pipeline_test_{expected_start:%Y%m%d}.csv"
    # Exclusive creation prevents accidental overwrite of an existing batch.
    with destination.open("x", encoding="utf-8", newline="") as handle:
        candidate.to_csv(handle, index=False)

    print(json.dumps({
        "status": "CREATED",
        "dataset_mode": "development",
        "synthetic": True,
        "candidate_path": str(destination),
        "rows": len(candidate),
        "first_hour_utc": str(expected_start),
        "last_hour_utc": str(latest + pd.Timedelta(hours=24)),
        "development_dataset_modified": False,
        "production_dataset_modified": False,
    }, indent=2))


if __name__ == "__main__":
    main()
