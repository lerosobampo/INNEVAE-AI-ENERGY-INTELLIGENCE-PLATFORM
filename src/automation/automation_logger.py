
"""
INNEVA.E - AUTOMATION EXECUTION LOGGER
Module 15 - Checkpoint 15.7C

Stores automation execution records in SQLite.

Production:
    Uses the INNEVA.E platform database.

Testing:
    Supports a temporary database through
    the INNEVAE_AUTOMATION_DB environment variable.
"""

import json
import os
import sqlite3

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "innevae_platform.db"
)


def get_database_path():
    """
    Return the configured database path.

    By default, use the production database.
    Tests can override it with an environment variable.
    """

    configured_path = os.environ.get(
        "INNEVAE_AUTOMATION_DB"
    )

    if configured_path:
        return Path(configured_path).expanduser()

    return DEFAULT_DATABASE_PATH


def initialize_execution_log():

    database_path = get_database_path()

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(database_path) as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_execution_log (
                execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                automation_name TEXT NOT NULL,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                status TEXT NOT NULL,
                report_path TEXT,
                metadata_path TEXT,
                executed_tools_json TEXT,
                validation_json TEXT,
                error_message TEXT
            )
            """
        )


def log_execution(
    automation_name,
    started_at_utc,
    finished_at_utc,
    status,
    report_path=None,
    metadata_path=None,
    executed_tools=None,
    validation=None,
    error_message=None,
):

    initialize_execution_log()

    with sqlite3.connect(
        get_database_path()
    ) as connection:

        cursor = connection.execute(
            """
            INSERT INTO automation_execution_log (
                automation_name,
                started_at_utc,
                finished_at_utc,
                status,
                report_path,
                metadata_path,
                executed_tools_json,
                validation_json,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                automation_name,
                started_at_utc,
                finished_at_utc,
                status,
                report_path,
                metadata_path,
                json.dumps(executed_tools or []),
                json.dumps(validation or {}),
                error_message,
            ),
        )

        return cursor.lastrowid


def get_execution_history(limit=10):

    initialize_execution_log()

    with sqlite3.connect(
        get_database_path()
    ) as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                execution_id,
                automation_name,
                started_at_utc,
                finished_at_utc,
                status,
                report_path,
                error_message
            FROM automation_execution_log
            ORDER BY execution_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


if __name__ == "__main__":

    initialize_execution_log()

    print("AUTOMATION EXECUTION LOG INITIALIZED")
    print(f"Database: {get_database_path()}")

    history = get_execution_history()

    print("\nCURRENT EXECUTION HISTORY")
    print(json.dumps(history, indent=2))
