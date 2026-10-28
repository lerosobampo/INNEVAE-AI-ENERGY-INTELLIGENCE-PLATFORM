
"""INNEVA.E — Checkpoint 20.6.4 Recovery Tests.

Tests forecast integrity without modifying existing artifacts.
"""

import copy
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import forecast_update_detector as detector


def run_tests():
    assessment = detector.detect_update(
        horizon="24h",
        method="auto",
    )

    assert assessment["status"] == "UP_TO_DATE", assessment

    record = detector.latest_successful_manifest(
        horizon="24h",
        method="auto",
    )

    assert record is not None

    original_file = Path(record["output_file"])

    assert original_file.is_file()

    original_hash = detector.sha256_file(original_file)

    with tempfile.TemporaryDirectory(
        prefix="innevae_forecast_test_"
    ) as directory:

        test_dir = Path(directory)

        test_file = test_dir / "forecast_copy.csv"

        test_file.write_bytes(original_file.read_bytes())

        test_record = copy.deepcopy(record)
        test_record["output_file"] = str(test_file)

        issue_time = record["issue_time_utc"]

        with patch.object(
            detector,
            "OUTPUT_DIR",
            test_dir,
        ):

            result = detector.validate_saved_forecast(
                test_record,
                "24h",
                issue_time,
            )

            assert result is None, result
            print("PASS: Valid forecast copy accepted")

            test_file.unlink()

            result = detector.validate_saved_forecast(
                test_record,
                "24h",
                issue_time,
            )

            assert result is not None
            assert "missing" in result.lower()
            print("PASS: Missing forecast detected")

            test_file.write_bytes(original_file.read_bytes())

            with test_file.open("ab") as handle:
                handle.write(b"\nCORRUPTED_TEST_DATA")

            result = detector.validate_saved_forecast(
                test_record,
                "24h",
                issue_time,
            )

            assert result is not None
            assert "checksum" in result.lower()
            print("PASS: Corrupted forecast detected")

            test_file.write_bytes(original_file.read_bytes())

            invalid_record = copy.deepcopy(test_record)
            invalid_record["output_sha256"] = "0" * 64

            result = detector.validate_saved_forecast(
                invalid_record,
                "24h",
                issue_time,
            )

            assert result is not None
            assert "checksum" in result.lower()
            print("PASS: Invalid manifest checksum detected")

    assert original_file.is_file()

    assert detector.sha256_file(original_file) == original_hash

    final_assessment = detector.detect_update(
        horizon="24h",
        method="auto",
    )

    assert final_assessment["status"] == "UP_TO_DATE"

    print("PASS: Original forecast remains unchanged")
    print("PASS: Forecast monitoring remains UP_TO_DATE")
    print()
    print("ALL FORECAST INTEGRITY TESTS PASSED")


if __name__ == "__main__":
    run_tests()
