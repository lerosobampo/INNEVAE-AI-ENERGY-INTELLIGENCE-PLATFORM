
"""
INNEVA.E - AGENT FAILURE RECOVERY TEST
Module 15 - Checkpoint 15.7C

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


class TestAutomationFailure(unittest.TestCase):

    def test_agent_failure_recovery(self):

        with tempfile.TemporaryDirectory() as directory:

            test_root = Path(directory)
            test_reports = test_root / "reports"
            test_database = test_root / "test_automation.db"

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
                return_value={
                    "status": "rejected",
                    "executed_tools": [
                        "get_energy_overview",
                    ],
                    "validation": {
                        "status": "fail",
                        "errors": [
                            "Simulated validation failure"
                        ],
                    },
                },
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

            self.assertIsNone(
                history[0]["report_path"],
            )

            self.assertEqual(
                list(test_reports.iterdir()),
                [],
            )

            self.assertTrue(
                test_database.exists()
            )

            print("\nISOLATED AGENT FAILURE TEST")
            print("-" * 50)
            print("Status:", result["status"])
            print("Test database:", test_database.name)
            print("Logged executions:", len(history))
            print("Remaining report files: 0")
            print("Production database modified: No")


if __name__ == "__main__":
    unittest.main(verbosity=2)
