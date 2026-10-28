
"""
INNEVA.E - PUBLICATION FAILURE RECOVERY TEST
Module 15 - Checkpoint 15.7C

Simulates a JSON publication failure.

Uses a temporary SQLite database and report directory.
"""

import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT / "src" / "automation"),
)

import generate_energy_report
from automation_logger import get_execution_history


class TestPublicationFailure(unittest.TestCase):

    def test_metadata_publication_failure(self):

        with tempfile.TemporaryDirectory() as directory:

            test_root = Path(directory)
            test_reports = test_root / "reports"
            test_database = test_root / "test_automation.db"

            fake_agent_result = {
                "status": "checks_passed",
                "report": "Synthetic test report.",
                "executed_tools": [
                    "get_energy_overview",
                    "get_data_quality",
                    "forecast_next_hour",
                ],
                "validation": {
                    "status": "pass",
                    "checks": {},
                    "errors": [],
                },
            }

            original_replace = Path.replace

            def simulated_replace(path, target):

                if str(target).endswith(".json"):
                    raise OSError(
                        "Simulated JSON publication failure"
                    )

                return original_replace(path, target)

            with patch.dict(
                os.environ,
                {
                    "INNEVAE_AUTOMATION_DB": str(
                        test_database
                    )
                },
            ), patch.object(
                generate_energy_report,
                "REPORTS_DIRECTORY",
                test_reports,
            ), patch.object(
                generate_energy_report,
                "run_agent",
                return_value=fake_agent_result,
            ), patch.object(
                Path,
                "replace",
                simulated_replace,
            ):

                result = (
                    generate_energy_report.generate_report()
                )

                history = get_execution_history()

            self.assertEqual(
                result["status"],
                "failed",
            )

            self.assertEqual(
                len(history),
                1,
            )

            self.assertEqual(
                history[0]["status"],
                "failed",
            )

            self.assertIn(
                "Simulated JSON publication failure",
                history[0]["error_message"],
            )

            self.assertEqual(
                list(test_reports.iterdir()),
                [],
            )

            print("\nISOLATED PUBLICATION FAILURE TEST")
            print("-" * 50)
            print("Status:", result["status"])
            print("Test database:", test_database.name)
            print("Logged executions:", len(history))
            print("Remaining report files: 0")
            print("Production database modified: No")


if __name__ == "__main__":
    unittest.main(verbosity=2)
