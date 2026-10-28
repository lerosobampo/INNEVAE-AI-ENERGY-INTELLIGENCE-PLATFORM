
"""INNEVA.E — Daily local data refresh runner.

Checkpoint 20.5C.3A:
- Records MANUAL or LAUNCHD execution source.
- Preserves historical JSONL records.
- Protects the production dataset with SHA-256 checks.
- Prevents concurrent daily runner executions.
- Uses the existing quality-gated manual refresh pipeline.
- Never generates synthetic data.
- Does not modify weekly automation configuration.

The execution_source field identifies how the runner was
invoked. It is not cryptographic proof of process identity.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PRODUCTION = (
    ROOT / "data" / "forecasting"
    / "energy_intelligence_hourly.csv"
)

DEVELOPMENT = (
    ROOT / "data" / "staging"
    / "energy_intelligence_hourly_development.csv"
)

INCOMING = ROOT / "data" / "refresh" / "incoming"

MANUAL_REFRESH = (
    ROOT / "src" / "automation"
    / "manual_data_refresh.py"
)

LOG_DIR = (
    ROOT / "reports" / "data_quality"
    / "daily_refresh"
)

RUN_LOG = LOG_DIR / "daily_refresh_runs.jsonl"
LOCK_FILE = LOG_DIR / "daily_refresh.lock"

EXPECTED_PRODUCTION_SHA256 = (
    "5b1c051071a497493a37121420c7ee5944814362464c"
    "394bc4082f306653684e"
)

VALID_SOURCES = {"MANUAL", "LAUNCHD"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def append_record(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with RUN_LOG.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                record,
                ensure_ascii=False,
            ) + "\n"
        )


def recent_records(limit: int = 10) -> list[dict]:
    if not RUN_LOG.is_file():
        return []

    records = []

    with RUN_LOG.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            if not line.strip():
                continue

            try:
                record = json.loads(line)

                if not isinstance(record, dict):
                    raise ValueError(
                        "Expected a JSON object"
                    )

                record.setdefault(
                    "execution_source",
                    "UNKNOWN",
                )

                records.append(record)

            except (
                json.JSONDecodeError,
                ValueError,
            ):
                records.append({
                    "status": "UNREADABLE_LOG_RECORD",
                    "execution_source": "UNKNOWN",
                    "raw": line.strip(),
                })

    return records[-limit:][::-1]


def verify_preflight() -> str:
    required_files = (
        PRODUCTION,
        DEVELOPMENT,
        MANUAL_REFRESH,
    )

    for path in required_files:
        if not path.is_file():
            raise FileNotFoundError(
                f"Required file missing: {path}"
            )

    if not INCOMING.is_dir():
        raise FileNotFoundError(
            f"Incoming directory missing: {INCOMING}"
        )

    actual_hash = sha256(PRODUCTION)

    if actual_hash != EXPECTED_PRODUCTION_SHA256:
        raise RuntimeError(
            "Production dataset SHA-256 does not match "
            "the protected baseline. Refresh stopped. "
            f"Actual: {actual_hash}"
        )

    return actual_hash


def run_refresh(
    execution_source: str = "MANUAL",
) -> int:
    if execution_source not in VALID_SOURCES:
        raise ValueError(
            f"Invalid execution source: {execution_source}"
        )

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOCK_FILE.open(
        "a+",
        encoding="utf-8",
    ) as lock:

        try:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

        except BlockingIOError:
            print(json.dumps({
                "status": "SKIPPED_ALREADY_RUNNING",
                "execution_source": execution_source,
                "checked_at_utc": now_utc(),
            }, indent=2))

            return 1

        record = {
            "started_at_utc": now_utc(),
            "finished_at_utc": None,
            "execution_source": execution_source,
            "status": "STARTED",
            "incoming_files_before": [],
            "incoming_files_after": [],
            "production_sha256_before": None,
            "production_sha256_after": None,
            "manual_refresh_returncode": None,
            "manual_refresh_stdout": "",
            "manual_refresh_stderr": "",
        }

        return_code = 1

        try:
            before_hash = verify_preflight()

            record[
                "production_sha256_before"
            ] = before_hash

            record["incoming_files_before"] = sorted(
                path.name
                for path in INCOMING.glob("*.csv")
                if path.is_file()
            )

            if not record["incoming_files_before"]:
                record["status"] = "NO_NEW_DATA"
                return_code = 0

            else:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(MANUAL_REFRESH),
                        "run",
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                record[
                    "manual_refresh_returncode"
                ] = result.returncode

                record[
                    "manual_refresh_stdout"
                ] = result.stdout

                record[
                    "manual_refresh_stderr"
                ] = result.stderr

                try:
                    response = json.loads(
                        result.stdout
                    )
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):
                    response = None

                if result.returncode != 0:
                    record["status"] = "REFRESH_ERROR"
                    return_code = 1

                elif not isinstance(response, dict):
                    record["status"] = (
                        "UNEXPECTED_REFRESH_OUTPUT"
                    )
                    return_code = 1

                else:
                    outcomes = response.get(
                        "results",
                        [],
                    )

                    if not isinstance(outcomes, list):
                        outcomes = []

                    all_applied = (
                        response.get("status") == "COMPLETE"
                        and bool(outcomes)
                        and all(
                            isinstance(item, dict)
                            and item.get("status") == "APPLIED"
                            for item in outcomes
                        )
                    )

                    if all_applied:
                        record["status"] = "COMPLETE"
                        return_code = 0
                    else:
                        record["status"] = (
                            "REFRESH_NOT_COMPLETE"
                        )
                        return_code = 1

        except Exception as error:
            record["status"] = "ERROR"
            record["error"] = (
                f"{type(error).__name__}: {error}"
            )
            return_code = 1

        finally:
            record["finished_at_utc"] = now_utc()

            try:
                if INCOMING.is_dir():
                    record[
                        "incoming_files_after"
                    ] = sorted(
                        path.name
                        for path in INCOMING.glob("*.csv")
                        if path.is_file()
                    )

                if PRODUCTION.is_file():
                    record[
                        "production_sha256_after"
                    ] = sha256(PRODUCTION)

                after_hash = record[
                    "production_sha256_after"
                ]

                if after_hash != EXPECTED_PRODUCTION_SHA256:
                    record["status"] = (
                        "CRITICAL_PRODUCTION_HASH_CHANGED"
                    )
                    return_code = 1

            except Exception as error:
                record["status"] = "ERROR"
                record["finalization_error"] = (
                    f"{type(error).__name__}: {error}"
                )
                return_code = 1

            try:
                append_record(record)
            finally:
                fcntl.flock(
                    lock.fileno(),
                    fcntl.LOCK_UN,
                )

            print(json.dumps(
                record,
                indent=2,
                ensure_ascii=False,
            ))

        return return_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="INNEVA.E daily data refresh"
    )

    parser.add_argument(
        "action",
        choices=[
            "run",
            "status",
            "history",
        ],
    )

    parser.add_argument(
        "--source",
        choices=["MANUAL", "LAUNCHD"],
        default="MANUAL",
        help=(
            "Execution provenance label. "
            "The LaunchAgent supplies LAUNCHD."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    if args.action == "run":
        return run_refresh(
            execution_source=args.source
        )

    if args.action == "history":
        print(json.dumps({
            "runs": recent_records(args.limit),
        }, indent=2))
        return 0

    if args.action == "status":
        latest = recent_records(1)

        print(json.dumps({
            "scheduler": "macOS launchd",
            "schedule": (
                "daily at 07:00 local time"
            ),
            "production_path": str(PRODUCTION),
            "development_path": str(DEVELOPMENT),
            "incoming_directory": str(INCOMING),
            "pending_csv_files": (
                sorted(
                    path.name
                    for path in INCOMING.glob("*.csv")
                    if path.is_file()
                )
                if INCOMING.is_dir()
                else None
            ),
            "latest_run": (
                latest[0] if latest else None
            ),
        }, indent=2))

        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
