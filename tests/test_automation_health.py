
"""
INNEVA.E - AUTOMATION HEALTH MONITOR TESTS
Module 15 - Checkpoint 15.9B

Tests:
1. Healthy automation
2. Warning after one failure
3. Critical after two consecutive failures
4. Critical when the latest report is overdue

Uses synthetic execution histories.
Does not modify the production database.
"""

import sys
import tempfile
import unittest

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT / "src" / "monitoring"),
)

import automation_health_monitor as monitor


class TestAutomationHealth(unittest.TestCase):

    def setUp(self):

        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.test_root = Path(
            self.temporary_directory.name
        )

        self.report_directory = (
            self.test_root / "reports"
        )

        self.report_directory.mkdir()

        self.report_path = (
            self.report_directory / "test_report.md"
        )

        self.report_path.write_text(
            "# Synthetic Energy Report\n",
            encoding="utf-8",
        )

        self.now = datetime(
            2026, 10, 24, 17, 0,
            tzinfo=timezone.utc,
        )

        self.project_patch = patch.object(
            monitor,
            "PROJECT_ROOT",
            self.test_root,
        )

        self.project_patch.start()

        self.addCleanup(
            self.project_patch.stop
        )

        self.addCleanup(
            self.temporary_directory.cleanup
        )

    def make_record(
        self,
        execution_id,
        status,
        hours_ago,
        report_path=None,
    ):

        finished_at = (
            self.now
            - timedelta(hours=hours_ago)
        ).isoformat()

        return {
            "execution_id": execution_id,
            "started_at_utc": finished_at,
            "finished_at_utc": finished_at,
            "status": status,
            "report_path": report_path,
            "error_message": (
                "Simulated failure"
                if status == "failed"
                else None
            ),
        }

    # --------------------------------------
    # TEST 1: HEALTHY
    # --------------------------------------

    def test_healthy(self):

        history = [
            self.make_record(
                1,
                "success",
                1,
                str(self.report_path),
            )
        ]

        result = monitor.evaluate_health(
            history,
            now=self.now,
        )

        self.assertEqual(
            result["health"],
            "healthy",
        )

        self.assertEqual(
            result["consecutive_failures"],
            0,
        )

    # --------------------------------------
    # TEST 2: WARNING
    # --------------------------------------

    def test_warning(self):

        history = [
            self.make_record(
                2,
                "failed",
                0.5,
            ),
            self.make_record(
                1,
                "success",
                1,
                str(self.report_path),
            ),
        ]

        result = monitor.evaluate_health(
            history,
            now=self.now,
        )

        self.assertEqual(
            result["health"],
            "warning",
        )

        self.assertEqual(
            result["consecutive_failures"],
            1,
        )

    # --------------------------------------
    # TEST 3: CRITICAL FAILURES
    # --------------------------------------

    def test_critical_consecutive_failures(self):

        history = [
            self.make_record(
                3,
                "failed",
                0.5,
            ),
            self.make_record(
                2,
                "failed",
                1,
            ),
            self.make_record(
                1,
                "success",
                2,
                str(self.report_path),
            ),
        ]

        result = monitor.evaluate_health(
            history,
            now=self.now,
        )

        self.assertEqual(
            result["health"],
            "critical",
        )

        self.assertEqual(
            result["consecutive_failures"],
            2,
        )

    # --------------------------------------
    # TEST 4: OVERDUE REPORT
    # --------------------------------------

    def test_critical_overdue_report(self):

        history = [
            self.make_record(
                1,
                "success",
                200,
                str(self.report_path),
            )
        ]

        result = monitor.evaluate_health(
            history,
            now=self.now,
        )

        self.assertEqual(
            result["health"],
            "critical",
        )

        self.assertGreater(
            result["latest_success_age_hours"],
            192,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
