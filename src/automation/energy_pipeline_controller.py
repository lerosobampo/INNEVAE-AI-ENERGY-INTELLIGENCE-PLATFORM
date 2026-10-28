
"""INNEVA.E — Energy Intelligence Pipeline Controller.

Coordinates the existing daily refresh and automated forecasting
systems without modifying their implementations.

Default mode:
- Runs a read-only integration check.
- Does not trigger ingestion.
- Does not generate new forecasts.

The 'run' action:
- Runs the existing quality-gated daily refresh.
- Proceeds only after a successful refresh result.
- Checks forecast readiness and integrity.
- Generates or recovers a forecast when required.

Development dataset only. Production dataset remains protected.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import forecast_update_detector as detector
import automated_forecast_runner as runner


ROOT = Path(__file__).resolve().parents[2]

AUTOMATION_DIR = ROOT / "src" / "automation"

DAILY_REFRESH_SCRIPT = (
    AUTOMATION_DIR / "daily_data_refresh.py"
)

PIPELINE_DIR = (
    ROOT / "reports" / "energy_pipeline"
)

PIPELINE_HISTORY = (
    PIPELINE_DIR / "pipeline_history.jsonl"
)

PIPELINE_LOCK = (
    PIPELINE_DIR / "pipeline.lock"
)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def emit(result):
    print(json.dumps(result, indent=2, default=str))


def append_history(record):
    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)

    with PIPELINE_HISTORY.open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(record) + "\n")


def read_history(limit=10):
    if not PIPELINE_HISTORY.is_file():
        return []

    records = []

    with PIPELINE_HISTORY.open(
        "r", encoding="utf-8"
    ) as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))

    return records[-limit:][::-1]


def run_daily_refresh():
    result = subprocess.run(
        [
            sys.executable,
            str(DAILY_REFRESH_SCRIPT),
            "run",
            "--source",
            "MANUAL",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            "Daily refresh returned invalid JSON: "
            + result.stdout[-1000:]
            + result.stderr[-1000:]
        )

    if not isinstance(payload, dict):
        raise RuntimeError(
            "Daily refresh returned an invalid response"
        )

    return result.returncode, payload


def check_pipeline(horizon="24h", method="auto"):
    assessment = detector.detect_update(
        horizon=horizon,
        method=method,
    )

    return {
        "component": "energy_pipeline",
        "action": "check",
        "checked_at_utc": now_utc(),
        "refresh_executed": False,
        "forecast_executed": False,
        "forecast_assessment": assessment,
        "status": assessment["status"],
    }


def run_pipeline(horizon="24h", method="auto"):
    PIPELINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with PIPELINE_LOCK.open("a+") as lock:
        try:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            return {
                "component": "energy_pipeline",
                "status": "ALREADY_RUNNING",
                "checked_at_utc": now_utc(),
            }

        record = {
            "component": "energy_pipeline",
            "started_at_utc": now_utc(),
            "finished_at_utc": None,
            "horizon": horizon,
            "requested_method": method,
            "refresh_executed": False,
            "forecast_executed": False,
            "status": "STARTED",
        }

        try:
            refresh_code, refresh = run_daily_refresh()

            record["refresh_executed"] = True
            record["refresh_status"] = refresh.get("status")
            record["refresh_returncode"] = refresh_code

            if (
                refresh_code != 0
                or refresh.get("status")
                not in {"COMPLETE", "NO_NEW_DATA"}
            ):
                record["status"] = "REFRESH_FAILED"
                return record

            assessment = detector.detect_update(
                horizon=horizon,
                method=method,
            )

            record["forecast_assessment_status"] = (
                assessment["status"]
            )

            if assessment["status"] == "BLOCKED":
                record["status"] = "FORECAST_BLOCKED"
                record["reason"] = assessment["reason"]
                return record

            if assessment["status"] == "UP_TO_DATE":
                record["status"] = "COMPLETE"
                record["forecast_status"] = "SKIPPED"
                return record

            if assessment["status"] not in {
                "READY",
                "RECOVERY_REQUIRED",
            }:
                raise RuntimeError(
                    "Unexpected forecast assessment: "
                    + assessment["status"]
                )

            forecast_result = runner.execute_forecast(
                horizon=horizon,
                method=method,
            )

            record["forecast_executed"] = True
            record["forecast_status"] = (
                forecast_result["status"]
            )
            record["forecast_id"] = (
                forecast_result.get("forecast_id")
            )

            if forecast_result["status"] not in {
                "SUCCESS",
                "SKIPPED",
            }:
                record["status"] = "FORECAST_FAILED"
                record["reason"] = (
                    forecast_result.get("reason")
                )
                return record

            final_assessment = detector.detect_update(
                horizon=horizon,
                method=method,
            )

            record["final_forecast_status"] = (
                final_assessment["status"]
            )

            if final_assessment["status"] != "UP_TO_DATE":
                record["status"] = "FORECAST_NOT_VERIFIED"
                record["reason"] = (
                    "Forecast execution did not produce "
                    "a fully verified output"
                )
                return record

            record["status"] = "COMPLETE"
            return record

        except Exception as error:
            record["status"] = "ERROR"
            record["error"] = (
                f"{type(error).__name__}: {error}"
            )
            return record

        finally:
            record["finished_at_utc"] = now_utc()
            append_history(record)
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )


def main():
    parser = argparse.ArgumentParser(
        description="INNEVA.E energy pipeline controller"
    )

    parser.add_argument(
        "action",
        choices=["check", "run", "history"],
    )

    parser.add_argument(
        "--horizon",
        choices=list(detector.SUPPORTED_HORIZONS),
        default="24h",
    )

    parser.add_argument(
        "--method",
        choices=sorted(detector.SUPPORTED_METHODS),
        default="auto",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    if args.action == "check":
        result = check_pipeline(
            horizon=args.horizon,
            method=args.method,
        )

    elif args.action == "history":
        result = {
            "component": "energy_pipeline",
            "runs": read_history(args.limit),
        }

    else:
        result = run_pipeline(
            horizon=args.horizon,
            method=args.method,
        )

    emit(result)

    return (
        0
        if result.get("status") not in {
            "BLOCKED",
            "REFRESH_FAILED",
            "FORECAST_BLOCKED",
            "FORECAST_FAILED",
            "FORECAST_NOT_VERIFIED",
            "ERROR",
            "ALREADY_RUNNING",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
