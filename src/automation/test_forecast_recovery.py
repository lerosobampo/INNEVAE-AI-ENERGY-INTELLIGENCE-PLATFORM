
"""INNEVA.E — Checkpoint 20.6.5: End-to-End Recovery Test.

Tests forecast detection and regeneration in a temporary
environment without modifying existing forecast artifacts,
production data, models, or scheduling services.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import forecast_update_detector as detector
import automated_forecast_runner as runner


def assert_status(result, expected):
    actual = result.get("status")
    assert actual == expected, (
        f"Expected {expected}, got {actual}: {result}"
    )


def run_tests():
    original_assessment = detector.detect_update(
        horizon="24h",
        method="auto",
    )
    assert_status(original_assessment, "UP_TO_DATE")

    original_record = detector.latest_successful_manifest(
        horizon="24h",
        method="auto",
    )
    assert original_record is not None

    original_file = Path(original_record["output_file"])
    original_sha = detector.sha256_file(original_file)
    original_manifest_sha = detector.sha256_file(
        detector.MANIFEST_FILE
    )

    with tempfile.TemporaryDirectory(
        prefix="innevae_recovery_"
    ) as directory:
        temp_root = Path(directory)
        temp_output = temp_root / "forecasts"
        temp_output.mkdir()

        temp_manifest = temp_root / "successful_forecasts.jsonl"
        temp_lock = temp_root / "forecast.lock"

        copied_forecast = (
            temp_output / original_file.name
        )
        copied_forecast.write_bytes(
            original_file.read_bytes()
        )

        copied_record = dict(original_record)
        copied_record["output_file"] = str(copied_forecast)

        temp_manifest.write_text(
            json.dumps(copied_record) + "\n",
            encoding="utf-8",
        )

        with (
            patch.object(
                detector, "MANIFEST_FILE", temp_manifest
            ),
            patch.object(
                detector, "OUTPUT_DIR", temp_output
            ),
            patch.object(
                runner, "MANIFEST_FILE", temp_manifest
            ),
            patch.object(
                runner, "OUTPUT_DIR", temp_output
            ),
            patch.object(
                runner, "LOCK_FILE", temp_lock
            ),
        ):
            healthy = detector.detect_update(
                horizon="24h",
                method="auto",
            )
            assert_status(healthy, "UP_TO_DATE")
            print("PASS: Isolated forecast initially healthy")

            copied_forecast.unlink()

            missing = detector.detect_update(
                horizon="24h",
                method="auto",
            )
            assert_status(missing, "RECOVERY_REQUIRED")
            print("PASS: Missing forecast triggers recovery")

            recovered = runner.execute_forecast(
                horizon="24h",
                method="auto",
            )
            assert_status(recovered, "SUCCESS")
            print("PASS: Missing forecast regenerated")

            after_recovery = detector.detect_update(
                horizon="24h",
                method="auto",
            )
            assert_status(after_recovery, "UP_TO_DATE")
            print("PASS: Healthy state restored")

            new_file = Path(recovered["output_file"])

            with new_file.open("ab") as handle:
                handle.write(b"\nTEST_CORRUPTION")

            corrupted = detector.detect_update(
                horizon="24h",
                method="auto",
            )
            assert_status(corrupted, "RECOVERY_REQUIRED")
            print("PASS: Corruption triggers recovery")

            recovered_again = runner.execute_forecast(
                horizon="24h",
                method="auto",
            )
            assert_status(recovered_again, "SUCCESS")
            print("PASS: Corrupted forecast regenerated")

            final = detector.detect_update(
                horizon="24h",
                method="auto",
            )
            assert_status(final, "UP_TO_DATE")
            print("PASS: Final forecast integrity verified")

            duplicate = runner.execute_forecast(
                horizon="24h",
                method="auto",
            )
            assert_status(duplicate, "SKIPPED")
            print("PASS: Duplicate execution prevented")

            records = [
                json.loads(line)
                for line in temp_manifest.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]

            assert len(records) == 3
            assert len({
                record["forecast_id"]
                for record in records
            }) == 3
            print("PASS: Recovery history preserved")

    assert original_file.is_file()
    assert detector.sha256_file(original_file) == original_sha
    assert (
        detector.sha256_file(detector.MANIFEST_FILE)
        == original_manifest_sha
    )

    original_final = detector.detect_update(
        horizon="24h",
        method="auto",
    )
    assert_status(original_final, "UP_TO_DATE")

    print("PASS: Original artifacts unchanged")
    print()
    print("ALL END-TO-END RECOVERY TESTS PASSED")


if __name__ == "__main__":
    run_tests()
