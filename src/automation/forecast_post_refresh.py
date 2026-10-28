"""Run development-only forecasting after today's successful launchd refresh.

Does not ingest data. Safe to invoke repeatedly; the existing forecast runner
checks the forecast manifest and output integrity before generating.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "src" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from forecast_update_detector import detect_update
from automated_forecast_runner import execute_forecast

REFRESH_HISTORY = ROOT / "reports" / "data_quality" / "daily_refresh" / "daily_refresh_runs.jsonl"
TIMEZONE = ZoneInfo("Europe/Amsterdam")
GOOD_REFRESH = {"COMPLETE", "NO_NEW_DATA"}


def latest_launchd_refresh():
    if not REFRESH_HISTORY.is_file():
        raise RuntimeError(f"Missing refresh history: {REFRESH_HISTORY}")
    latest = None
    with REFRESH_HISTORY.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid refresh history JSON at line {number}") from exc
            if record.get("execution_source") == "LAUNCHD":
                latest = record
    return latest


def run(*, check_only=False):
    now = datetime.now(timezone.utc)
    today = now.astimezone(TIMEZONE).date()
    latest = latest_launchd_refresh()
    output = {
        "component": "forecast_post_refresh",
        "checked_at_utc": now.isoformat(),
        "local_date": today.isoformat(),
        "refresh_status": latest.get("status") if latest else None,
    }
    if not latest:
        return {**output, "status": "BLOCKED", "reason": "No launchd refresh history found"}
    try:
        started = datetime.fromisoformat(latest["started_at_utc"].replace("Z", "+00:00"))
        if started.tzinfo is None:
            raise ValueError("Refresh timestamp is timezone naive")
    except (KeyError, ValueError, TypeError) as exc:
        return {**output, "status": "BLOCKED", "reason": f"Invalid refresh timestamp: {exc}"}
    if started.astimezone(TIMEZONE).date() != today:
        return {**output, "status": "BLOCKED", "reason": "No launchd refresh run today"}
    if latest.get("status") not in GOOD_REFRESH:
        return {**output, "status": "BLOCKED", "reason": "Latest launchd refresh did not succeed"}
    if latest.get("production_sha256_before") != latest.get("production_sha256_after"):
        return {**output, "status": "BLOCKED", "reason": "Production checksum changed during refresh"}
    assessment = detect_update(horizon="24h", method="auto")
    output["forecast_assessment_status"] = assessment["status"]
    if assessment["status"] == "BLOCKED":
        return {**output, "status": "BLOCKED", "reason": assessment.get("reason", "Forecast detector blocked")}
    if assessment["status"] == "UP_TO_DATE":
        return {**output, "status": "SKIPPED", "reason": "Verified forecast already exists"}
    if check_only:
        return {**output, "status": "READY", "reason": "Forecast execution required; check-only mode"}
    if assessment["status"] not in {"READY", "RECOVERY_REQUIRED"}:
        return {**output, "status": "BLOCKED", "reason": "Unexpected detector status"}
    result = execute_forecast(horizon="24h", method="auto")
    output["forecast_status"] = result.get("status")
    output["forecast_id"] = result.get("forecast_id")
    if result.get("status") not in {"SUCCESS", "SKIPPED"}:
        return {**output, "status": "ERROR", "reason": result.get("reason", result.get("message", "Forecast runner failed"))}
    final = detect_update(horizon="24h", method="auto")
    output["final_forecast_status"] = final["status"]
    if final["status"] != "UP_TO_DATE":
        return {**output, "status": "ERROR", "reason": "Final forecast verification failed"}
    return {**output, "status": "COMPLETE"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "run"])
    args = parser.parse_args()
    try:
        result = run(check_only=args.action == "check")
    except Exception as exc:
        result = {"component": "forecast_post_refresh", "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"SKIPPED", "COMPLETE", "READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
