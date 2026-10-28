"""INNEVA.E — Checkpoint 20.6.3: Automated Forecast Runner.

Generates development-only historical energy forecasts using
the existing unified forecasting engine.

Safety:
- Never modifies the production dataset.
- Never retrains or overwrites existing models.
- Never modifies the original forecast registry.
- Uses a separate development output directory and manifest.
- Prevents overlapping executions with a file lock.
- Validates source integrity before and after forecasting.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from forecast_update_detector import (
    DEVELOPMENT_CSV,
    MANIFEST_FILE,
    SUPPORTED_HORIZONS,
    check_production_integrity,
    detect_update,
    sha256_file,
    validate_saved_forecast,
)

ROOT = Path(__file__).resolve().parents[2]
FORECASTING_DIR = ROOT / "src" / "forecasting"

if str(FORECASTING_DIR) not in sys.path:
    sys.path.insert(0, str(FORECASTING_DIR))

from unified_forecast_engine import forecast

OUTPUT_DIR = (
    ROOT / "data" / "processed"
    / "automated_forecasting_development"
)

LOCK_FILE = (
    ROOT / "reports" / "forecast_automation"
    / "automated_forecast.lock"
)

VALID_METHODS = {
    "auto",
    "recursive_ml",
    "direct_ml",
    "daily_naive",
    "weekly_naive",
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def print_result(result):
    print(json.dumps(result, indent=2, default=str))


@contextmanager
def execution_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_FILE.open("a+") as handle:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as error:
            raise RuntimeError(
                "Another automated forecast execution is running"
            ) from error

        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_development_history():
    df = pd.read_csv(
        DEVELOPMENT_CSV,
        usecols=["hour_start_utc", "actual_load_mw"],
    )

    df["hour_start_utc"] = pd.to_datetime(
        df["hour_start_utc"],
        utc=True,
        errors="raise",
        format="mixed",
    )

    df["actual_load_mw"] = pd.to_numeric(
        df["actual_load_mw"],
        errors="coerce",
    )

    return df


def validate_predictions(df, horizon, issue_time):
    expected_count = SUPPORTED_HORIZONS[horizon]

    required = {
        "issue_time_utc",
        "forecast_time_utc",
        "horizon",
        "requested_method",
        "selected_method",
        "step",
        "predicted_demand_mw",
    }

    if not required.issubset(df.columns):
        raise ValueError(
            "Forecast output is missing required columns"
        )

    if len(df) != expected_count:
        raise ValueError(
            f"Expected {expected_count} predictions; got {len(df)}"
        )

    issue_times = pd.to_datetime(
        df["issue_time_utc"], utc=True
    )

    target_times = pd.to_datetime(
        df["forecast_time_utc"], utc=True
    )

    expected_issue = pd.Timestamp(issue_time)

    if not (issue_times == expected_issue).all():
        raise ValueError("Forecast issue timestamp mismatch")

    expected_targets = pd.date_range(
        start=expected_issue,
        periods=expected_count,
        freq="h",
    )

    if not pd.DatetimeIndex(target_times).equals(
        expected_targets
    ):
        raise ValueError("Forecast target timestamps mismatch")

    expected_steps = np.arange(1, expected_count + 1)

    if not np.array_equal(
        df["step"].to_numpy(),
        expected_steps,
    ):
        raise ValueError("Forecast step sequence is invalid")

    predictions = pd.to_numeric(
        df["predicted_demand_mw"],
        errors="raise",
    ).to_numpy(dtype=float)

    if not np.isfinite(predictions).all():
        raise ValueError("Forecast contains non-finite predictions")

    if (predictions <= 0).any():
        raise ValueError("Forecast contains non-positive demand")

    if df["horizon"].nunique() != 1:
        raise ValueError("Forecast horizon is inconsistent")

    if df["horizon"].iloc[0] != horizon:
        raise ValueError("Forecast horizon mismatch")

    if df["selected_method"].nunique() != 1:
        raise ValueError("Multiple selected methods detected")

    if df["requested_method"].nunique() != 1:
        raise ValueError("Multiple requested methods detected")

    return {
        "prediction_count": int(len(df)),
        "minimum_demand_mw": float(predictions.min()),
        "maximum_demand_mw": float(predictions.max()),
        "average_demand_mw": float(predictions.mean()),
        "selected_method": str(
            df["selected_method"].iloc[0]
        ),
    }


def read_manifest():
    if not MANIFEST_FILE.exists():
        return []

    records = []

    with MANIFEST_FILE.open(
        "r", encoding="utf-8"
    ) as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid manifest JSON at line {line_number}"
                ) from error

            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid manifest record at line {line_number}"
                )

            records.append(record)

    return records


def matching_forecast(records, horizon, method, fingerprint, issue_time):
    """Return a saved forecast matching the current detector configuration."""
    from forecast_update_detector import AUTO_METHODS

    expected_selected = (
        AUTO_METHODS[horizon]
        if method == "auto"
        else method
    )

    for record in reversed(records):
        if not (
            record.get("status") == "SUCCESS"
            and record.get("dataset_mode") == "development"
            and record.get("horizon") == horizon
            and record.get("requested_method") == method
            and record.get("selected_method") == expected_selected
            and record.get("dataset_sha256") == fingerprint
            and record.get("issue_time_utc") == issue_time
        ):
            continue

        issue = pd.Timestamp(issue_time)

        if validate_saved_forecast(record, horizon, issue) is None:
            return record

    return None


def append_manifest(record):
    MANIFEST_FILE.parent.mkdir(
        parents=True, exist_ok=True
    )

    with MANIFEST_FILE.open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def execute_forecast(horizon="24h", method="auto"):
    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")

    if method not in VALID_METHODS:
        raise ValueError(f"Unsupported method: {method}")

    with execution_lock():
        assessment = detect_update(horizon, method)

        if assessment["status"] == "BLOCKED":
            return {
                "checkpoint": "20.6.3",
                "status": "BLOCKED",
                "reason": assessment["reason"],
                "generated_at_utc": now_utc(),
            }

        dataset = assessment["dataset"]
        fingerprint = dataset["dataset_sha256"]
        issue_time = dataset["proposed_issue_time_utc"]

        records = read_manifest()

        previous = matching_forecast(
            records,
            horizon,
            method,
            fingerprint,
            issue_time,
        )

        if assessment["status"] == "UP_TO_DATE" and previous is None:
            raise RuntimeError("Detector and runner disagree on verified forecast")

        if previous is not None:
            return {
                "checkpoint": "20.6.3",
                "status": "SKIPPED",
                "reason": "Matching verified forecast already exists",
                "forecast_id": previous["forecast_id"],
                "output_file": previous["output_file"],
                "dataset_sha256": fingerprint,
                "issue_time_utc": issue_time,
                "horizon": horizon,
                "requested_method": method,
            }

        source_sha_before = sha256_file(DEVELOPMENT_CSV)

        if source_sha_before != fingerprint:
            raise RuntimeError(
                "Development dataset changed during readiness assessment"
            )

        history = load_development_history()

        result = forecast(
            issue_time=issue_time,
            horizon=horizon,
            method=method,
            historical_data=history,
        )

        statistics = validate_predictions(
            result,
            horizon,
            issue_time,
        )

        if str(result["requested_method"].iloc[0]) != method:
            raise ValueError("Forecast requested method mismatch")

        expected_selected = assessment.get("expected_selected_method")
        if expected_selected and statistics["selected_method"] != expected_selected:
            raise ValueError(
                "Forecast selected method differs from detector expectation: "
                f"{statistics['selected_method']} != {expected_selected}"
            )

        source_sha_after = sha256_file(DEVELOPMENT_CSV)

        if source_sha_after != source_sha_before:
            raise RuntimeError(
                "Development dataset changed during forecasting"
            )

        integrity = check_production_integrity()

        if integrity["status"] != "PASS":
            raise RuntimeError(
                "Protected production integrity check failed"
            )

        forecast_id = str(uuid.uuid4())

        OUTPUT_DIR.mkdir(
            parents=True, exist_ok=True
        )

        output_file = (
            OUTPUT_DIR
            / f"forecast_{horizon}_{forecast_id}.csv"
        )

        temporary_file = (
            OUTPUT_DIR
            / f".forecast_{forecast_id}.tmp"
        )

        try:
            result.to_csv(
                temporary_file,
                index=False,
            )

            output_sha = sha256_file(temporary_file)

            if output_file.exists():
                raise FileExistsError(
                    f"Forecast output already exists: {output_file}"
                )

            # Create the final file without replacing an
            # existing artifact.
            os.link(temporary_file, output_file)
        finally:
            temporary_file.unlink(missing_ok=True)

        record = {
            "forecast_id": forecast_id,
            "status": "SUCCESS",
            "dataset_mode": "development",
            "dataset_path": str(DEVELOPMENT_CSV),
            "dataset_sha256": fingerprint,
            "issue_time_utc": issue_time,
            "horizon": horizon,
            "requested_method": method,
            "selected_method": statistics["selected_method"],
            "prediction_count": statistics["prediction_count"],
            "minimum_demand_mw": statistics["minimum_demand_mw"],
            "maximum_demand_mw": statistics["maximum_demand_mw"],
            "average_demand_mw": statistics["average_demand_mw"],
            "output_file": str(output_file),
            "output_sha256": output_sha,
            "generated_at_utc": now_utc(),
            "forecast_type": "historical_development_scenario",
        }

        append_manifest(record)

        return {
            "checkpoint": "20.6.3",
            **record,
        }


def show_history(limit=5):
    records = read_manifest()

    return {
        "checkpoint": "20.6.3",
        "total_recorded_forecasts": len(records),
        "forecasts": records[-limit:][::-1],
    }


def main():
    parser = argparse.ArgumentParser(
        description="INNEVA.E automated forecast runner"
    )

    parser.add_argument(
        "action",
        choices=["run", "check", "history"],
    )

    parser.add_argument(
        "--horizon",
        choices=list(SUPPORTED_HORIZONS),
        default="24h",
    )

    parser.add_argument(
        "--method",
        choices=sorted(VALID_METHODS),
        default="auto",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    try:
        if args.action == "check":
            result = detect_update(args.horizon, args.method)

        elif args.action == "history":
            if args.limit < 1:
                raise ValueError("--limit must be positive")

            result = show_history(args.limit)

        else:
            result = execute_forecast(
                horizon=args.horizon,
                method=args.method,
            )

        print_result(result)

        if result.get("status") in {"BLOCKED", "ERROR"}:
            return 1

        return 0

    except Exception as error:
        print_result({
            "checkpoint": "20.6.3",
            "status": "ERROR",
            "error_type": type(error).__name__,
            "message": str(error),
            "generated_at_utc": now_utc(),
        })

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
