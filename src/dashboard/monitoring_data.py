
"""
INNEVA.E - MONITORING DATA LOADER
Module 16 - Checkpoint 16.5A

Read-only access to the automation execution log.

This module does not run automations,
modify execution records, or change
the existing health monitor.
"""

import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "innevae_platform.db"
)

AUTOMATION_NAME = "energy_intelligence_report"


def get_monitoring_connection():
    """
    Open the SQLite database in read-only mode.
    """

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Monitoring database not found: {DATABASE_PATH}"
        )

    return sqlite3.connect(
        DATABASE_PATH.resolve().as_uri() + "?mode=ro",
        uri=True,
    )


def load_execution_history():
    """
    Load all report automation executions.

    Returns newest execution first.
    """

    query = """
        SELECT
            execution_id,
            automation_name,
            started_at_utc,
            finished_at_utc,
            status,
            report_path,
            metadata_path,
            executed_tools_json,
            validation_json,
            error_message
        FROM automation_execution_log
        WHERE automation_name = ?
        ORDER BY execution_id DESC
    """

    with get_monitoring_connection() as connection:
        df = pd.read_sql_query(
            query,
            connection,
            params=(AUTOMATION_NAME,),
        )

    return df


def calculate_execution_metrics(history):
    """
    Calculate summary statistics from
    automation execution history.
    """

    total = len(history)

    successful = int(
        (history["status"] == "success").sum()
    )

    failed = int(
        (history["status"] == "failed").sum()
    )

    success_rate = (
        successful / total * 100
        if total > 0
        else 0.0
    )

    return {
        "total_executions": total,
        "successful_executions": successful,
        "failed_executions": failed,
        "success_rate_pct": round(
            success_rate,
            2,
        ),
    }


def inspect_execution_history():

    history = load_execution_history()

    metrics = calculate_execution_metrics(
        history
    )

    print("=" * 65)
    print("INNEVA.E - AUTOMATION EXECUTION HISTORY")
    print("=" * 65)

    for key, value in metrics.items():
        print(f"{key}: {value}")

    print("\nRecent executions:")

    if history.empty:
        print("No executions found.")
    else:
        columns = [
            "execution_id",
            "status",
            "started_at_utc",
            "error_message",
        ]

        print(
            history[columns]
            .head(10)
            .to_string(index=False)
        )


if __name__ == "__main__":
    inspect_execution_history()
