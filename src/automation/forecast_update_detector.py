
"""INNEVA.E — Checkpoint 20.6.4: Forecast Integrity Monitor.

Read-only development forecast assessment.

Verifies:
- Protected production dataset SHA-256
- Development dataset readiness
- Forecast horizon and requested method
- Source dataset fingerprint
- Forecast issue timestamp
- Saved forecast existence and checksum
- Saved forecast contents and prediction integrity

Never modifies datasets, forecasts, models, registries,
manifests, or macOS scheduling services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

DEVELOPMENT_CSV = (
    ROOT / "data/staging/energy_intelligence_hourly_development.csv"
)

PRODUCTION_CSV = (
    ROOT / "data/forecasting/energy_intelligence_hourly.csv"
)

EXPECTED_PRODUCTION_SHA256 = (
    "5b1c051071a497493a37121420c7ee5944814362464c394bc4082f306653684e"
)

MANIFEST_FILE = (
    ROOT / "reports/forecast_automation/successful_forecasts.jsonl"
)

OUTPUT_DIR = (
    ROOT / "data/processed/automated_forecasting_development"
)

SUPPORTED_HORIZONS = {
    "1h": 1,
    "24h": 24,
    "7d": 168,
    "30d": 720,
}

SUPPORTED_METHODS = {
    "auto",
    "recursive_ml",
    "direct_ml",
    "daily_naive",
    "weekly_naive",
}

AUTO_METHODS = {
    "1h": "recursive_ml",
    "24h": "recursive_ml",
    "7d": "recursive_ml",
    "30d": "direct_ml",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def check_production_integrity():
    if not PRODUCTION_CSV.is_file():
        return {
            "status": "FAIL",
            "reason": "Protected production dataset is missing",
        }

    actual = sha256_file(PRODUCTION_CSV)

    return {
        "status": (
            "PASS"
            if actual == EXPECTED_PRODUCTION_SHA256
            else "FAIL"
        ),
        "expected_sha256": EXPECTED_PRODUCTION_SHA256,
        "actual_sha256": actual,
    }


def inspect_development_dataset():
    if not DEVELOPMENT_CSV.is_file():
        raise FileNotFoundError(
            f"Development dataset missing: {DEVELOPMENT_CSV}"
        )

    if DEVELOPMENT_CSV.resolve() == PRODUCTION_CSV.resolve():
        raise ValueError(
            "Development dataset cannot be the production dataset"
        )

    fingerprint = sha256_file(DEVELOPMENT_CSV)

    df = pd.read_csv(
        DEVELOPMENT_CSV,
        usecols=["hour_start_utc", "actual_load_mw"],
    )

    if df.empty:
        raise ValueError("Development dataset is empty")

    df["hour_start_utc"] = pd.to_datetime(
        df["hour_start_utc"],
        utc=True,
        errors="raise",
        format="mixed",
    )

    if df["hour_start_utc"].isna().any():
        raise ValueError("Missing timestamps detected")

    df["actual_load_mw"] = pd.to_numeric(
        df["actual_load_mw"],
        errors="coerce",
    )

    df = df.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    if df["hour_start_utc"].duplicated().any():
        raise ValueError("Duplicate hourly timestamps detected")

    timestamps = df["hour_start_utc"]

    if (
        timestamps.diff().dropna()
        != pd.Timedelta(hours=1)
    ).any():
        raise ValueError(
            "Development dataset has missing or irregular hours"
        )

    latest = timestamps.iloc[-1]
    issue_time = latest + pd.Timedelta(hours=1)
    recent = df.tail(168).copy()

    continuous_history = False
    valid_demand = False

    if len(recent) == 168:
        expected = pd.date_range(
            end=latest,
            periods=168,
            freq="h",
        )

        continuous_history = (
            pd.DatetimeIndex(
                recent["hour_start_utc"]
            ).equals(expected)
        )

        values = recent[
            "actual_load_mw"
        ].to_numpy(dtype=float)

        valid_demand = all(
            math.isfinite(float(value))
            and float(value) > 0
            for value in values
        )

    return {
        "dataset_path": str(DEVELOPMENT_CSV),
        "dataset_sha256": fingerprint,
        "total_rows": int(len(df)),
        "first_observation_utc": (
            timestamps.iloc[0].isoformat()
        ),
        "latest_observation_utc": latest.isoformat(),
        "proposed_issue_time_utc": issue_time.isoformat(),
        "recent_history_rows": int(len(recent)),
        "continuous_168h_history": continuous_history,
        "valid_recent_demand": valid_demand,
        "forecast_ready": (
            continuous_history and valid_demand
        ),
    }


def read_manifest():
    if not MANIFEST_FILE.is_file():
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


def latest_successful_manifest(horizon, method="auto"):
    """Compatibility interface for earlier checkpoint code."""

    matching = [
        record
        for record in read_manifest()
        if (
            record.get("status") == "SUCCESS"
            and record.get("dataset_mode") == "development"
            and record.get("horizon") == horizon
            and record.get("requested_method") == method
        )
    ]

    return matching[-1] if matching else None


def validate_saved_forecast(record, horizon, issue_time):
    """Return a reason if the saved forecast is invalid."""

    output = record.get("output_file")

    if not isinstance(output, str) or not output:
        return "Forecast output path is missing"

    path = Path(output)

    try:
        resolved = path.resolve()
        resolved.relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return "Forecast output is outside development directory"

    if not resolved.is_file():
        return "Forecast output file is missing"

    expected_sha = record.get("output_sha256")

    if not isinstance(expected_sha, str) or not expected_sha:
        return "Forecast output checksum is missing"

    if sha256_file(resolved) != expected_sha:
        return "Forecast output checksum mismatch"

    try:
        df = pd.read_csv(resolved)

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
            return "Forecast output columns are incomplete"

        expected_count = SUPPORTED_HORIZONS[horizon]

        if len(df) != expected_count:
            return "Forecast prediction count is incorrect"

        issue_times = pd.to_datetime(
            df["issue_time_utc"],
            utc=True,
            errors="raise",
        )

        if issue_times.isna().any():
            return "Invalid forecast issue timestamps"

        expected_issue = pd.Timestamp(issue_time)

        if not (issue_times == expected_issue).all():
            return "Forecast issue timestamp mismatch"

        targets = pd.to_datetime(
            df["forecast_time_utc"],
            utc=True,
            errors="raise",
        )

        expected_targets = pd.date_range(
            start=expected_issue,
            periods=expected_count,
            freq="h",
        )

        if not pd.DatetimeIndex(targets).equals(
            expected_targets
        ):
            return "Forecast target timestamps are invalid"

        steps = pd.to_numeric(
            df["step"],
            errors="raise",
        ).to_numpy()

        if not (
            steps == list(range(1, expected_count + 1))
        ).all():
            return "Forecast step sequence is invalid"

        predictions = pd.to_numeric(
            df["predicted_demand_mw"],
            errors="raise",
        ).to_numpy(dtype=float)

        if not all(
            math.isfinite(float(value))
            and float(value) > 0
            for value in predictions
        ):
            return "Forecast predictions contain invalid values"

        for column, expected_value in (
            ("horizon", horizon),
            ("requested_method", record.get("requested_method")),
            ("selected_method", record.get("selected_method")),
        ):
            if not (df[column] == expected_value).all():
                return f"Forecast {column} mismatch"

        if record.get("prediction_count") != expected_count:
            return "Manifest prediction count mismatch"

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        pd.errors.ParserError,
    ) as error:
        return f"Forecast output validation failed: {error}"

    return None


def detect_update(horizon="24h", method="auto"):
    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")

    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported method: {method}")

    integrity = check_production_integrity()

    result = {
        "checkpoint": "20.6.4",
        "checked_at_utc": utc_now(),
        "dataset_mode": "development",
        "horizon": horizon,
        "requested_method": method,
        "expected_selected_method": (
            AUTO_METHODS[horizon]
            if method == "auto"
            else method
        ),
        "production_integrity": integrity,
    }

    if integrity["status"] != "PASS":
        result.update({
            "status": "BLOCKED",
            "reason": "Production integrity check failed",
            "update_required": False,
        })
        return result

    try:
        dataset = inspect_development_dataset()
    except (
        OSError,
        ValueError,
        KeyError,
        pd.errors.ParserError,
    ) as error:
        result.update({
            "status": "BLOCKED",
            "reason": f"Development dataset validation failed: {error}",
            "update_required": False,
        })
        return result

    result["dataset"] = dataset

    if not dataset["forecast_ready"]:
        result.update({
            "status": "BLOCKED",
            "reason": (
                "Insufficient continuous, valid demand history"
            ),
            "update_required": False,
        })
        return result

    try:
        records = read_manifest()
    except (OSError, ValueError) as error:
        result.update({
            "status": "BLOCKED",
            "reason": f"Forecast manifest error: {error}",
            "update_required": False,
        })
        return result

    relevant = [
        record
        for record in records
        if (
            record.get("status") == "SUCCESS"
            and record.get("dataset_mode") == "development"
            and record.get("horizon") == horizon
            and record.get("requested_method") == method
            and record.get("selected_method")
            == result["expected_selected_method"]
        )
    ]

    fingerprint = dataset["dataset_sha256"]
    issue_time = dataset["proposed_issue_time_utc"]

    matching = [
        record
        for record in relevant
        if (
            record.get("dataset_sha256") == fingerprint
            and record.get("issue_time_utc") == issue_time
        )
    ]

    if not matching:
        result.update({
            "status": "READY",
            "reason": (
                "No successful forecast matches the current "
                "dataset, issue time, horizon and method"
            ),
            "update_required": True,
            "previous_forecast": None,
        })
        return result

    invalid_reasons = []

    for record in reversed(matching):
        invalid_reason = validate_saved_forecast(
            record,
            horizon,
            issue_time,
        )

        if invalid_reason is None:
            result.update({
                "status": "UP_TO_DATE",
                "reason": "Matching forecast verified successfully",
                "update_required": False,
                "previous_forecast": {
                    "forecast_id": record.get("forecast_id"),
                    "output_file": record.get("output_file"),
                    "output_sha256": record.get("output_sha256"),
                    "dataset_sha256": fingerprint,
                    "issue_time_utc": issue_time,
                },
            })
            return result

        invalid_reasons.append(invalid_reason)

    result.update({
        "status": "RECOVERY_REQUIRED",
        "reason": (
            "Matching forecast records exist, but no "
            "valid forecast output could be verified"
        ),
        "integrity_issues": invalid_reasons,
        "update_required": True,
        "previous_forecast": {
            "forecast_id": matching[-1].get("forecast_id"),
            "output_file": matching[-1].get("output_file"),
        },
    })

    return result


def main():
    parser = argparse.ArgumentParser(
        description="INNEVA.E forecast integrity monitor"
    )

    parser.add_argument(
        "action",
        choices=["check"],
    )

    parser.add_argument(
        "--horizon",
        choices=list(SUPPORTED_HORIZONS),
        default="24h",
    )

    parser.add_argument(
        "--method",
        choices=sorted(SUPPORTED_METHODS),
        default="auto",
    )

    args = parser.parse_args()

    result = detect_update(
        horizon=args.horizon,
        method=args.method,
    )

    print(json.dumps(result, indent=2))

    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
