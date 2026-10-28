
"""Regression tests for scheduled refresh monitoring.

Uses synthetic in-memory execution records.
Does not modify datasets, SQLite, or launchd.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from refresh_monitor import (
    scheduled_execution_state,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(
        value
    ).astimezone(timezone.utc)


def execution(
    started: str,
    finished: str | None,
    status: str,
    source: str = "LAUNCHD",
) -> dict:
    return {
        "started_at_utc": started,
        "finished_at_utc": finished,
        "status": status,
        "execution_source": source,
    }


class ScheduledRefreshTests(
    unittest.TestCase
):
    def test_before_first_schedule(self):
        result = scheduled_execution_state(
            utc("2026-10-26T18:00:00+00:00"),
            [],
        )

        self.assertEqual(
            result["status"],
            "NOT_DUE",
        )

    def test_before_first_deadline(self):
        result = scheduled_execution_state(
            utc("2026-10-27T06:30:00+00:00"),
            [],
        )

        self.assertEqual(
            result["status"],
            "NOT_DUE",
        )

    def test_missed_schedule(self):
        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            [],
        )

        self.assertEqual(
            result["status"],
            "MISSED",
        )

    def test_successful_on_time(self):
        records = [
            execution(
                "2026-10-27T06:05:00+00:00",
                "2026-10-27T06:05:10+00:00",
                "NO_NEW_DATA",
            )
        ]

        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "VERIFIED",
        )

    def test_failed_on_time(self):
        records = [
            execution(
                "2026-10-27T06:05:00+00:00",
                "2026-10-27T06:05:10+00:00",
                "REFRESH_ERROR",
            )
        ]

        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "FAILED",
        )

    def test_successful_late(self):
        records = [
            execution(
                "2026-10-27T07:30:00+00:00",
                "2026-10-27T07:30:10+00:00",
                "NO_NEW_DATA",
            )
        ]

        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "LATE",
        )

    def test_manual_does_not_verify(self):
        records = [
            execution(
                "2026-10-27T06:05:00+00:00",
                "2026-10-27T06:05:10+00:00",
                "NO_NEW_DATA",
                source="MANUAL",
            )
        ]

        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "MISSED",
        )

    def test_missing_completion(self):
        records = [
            execution(
                "2026-10-27T06:05:00+00:00",
                None,
                "NO_NEW_DATA",
            )
        ]

        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "UNVERIFIED",
        )

    def test_success_overrides_failure(self):
        records = [
            execution(
                "2026-10-27T06:01:00+00:00",
                "2026-10-27T06:01:10+00:00",
                "REFRESH_ERROR",
            ),
            execution(
                "2026-10-27T06:10:00+00:00",
                "2026-10-27T06:10:10+00:00",
                "COMPLETE",
            ),
        ]

        result = scheduled_execution_state(
            utc("2026-10-27T08:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "VERIFIED",
        )

    def test_previous_day_is_checked(self):
        records = [
            execution(
                "2026-10-27T06:05:00+00:00",
                "2026-10-27T06:05:10+00:00",
                "COMPLETE",
            )
        ]

        result = scheduled_execution_state(
            utc("2026-10-28T05:00:00+00:00"),
            records,
        )

        self.assertEqual(
            result["status"],
            "VERIFIED",
        )

        self.assertEqual(
            result["latest_due_date"],
            "2026-10-27",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
