
"""
INNEVA.E — Forecast Registry
Module 17.7A

Stores forecast runs and hourly predictions in SQLite.

Features:
- Separate forecasting database
- Unique forecast IDs
- Model artifact identification
- Atomic database transactions
- Forecast retrieval
- Duplicate-safe primary keys
- Historical and future forecast support
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import uuid

import joblib
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data/forecasting/forecast_registry.sqlite"
)

MODELS_DIR = PROJECT_ROOT / "models"

MODEL_FILES = {
    "recursive_ml": (
        MODELS_DIR / "historical_demand_final.joblib"
    ),
    "direct_ml": (
        MODELS_DIR / "direct_demand_final.joblib"
    ),
}

VALID_HORIZONS = {
    "1h": 1,
    "24h": 24,
    "7d": 168,
    "30d": 720,
}

VALID_METHODS = {
    "recursive_ml",
    "direct_ml",
    "daily_naive",
    "weekly_naive",
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_registry():

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_runs (
                forecast_id TEXT PRIMARY KEY,
                created_at_utc TEXT NOT NULL,
                issue_time_utc TEXT NOT NULL,
                horizon TEXT NOT NULL,
                requested_method TEXT NOT NULL,
                selected_method TEXT NOT NULL,
                model_version TEXT NOT NULL,
                prediction_count INTEGER NOT NULL
                    CHECK (prediction_count > 0)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_predictions (
                forecast_id TEXT NOT NULL,
                forecast_time_utc TEXT NOT NULL,
                step INTEGER NOT NULL
                    CHECK (step > 0),
                predicted_demand_mw REAL NOT NULL
                    CHECK (predicted_demand_mw > 0),

                PRIMARY KEY (forecast_id, step),

                FOREIGN KEY (forecast_id)
                    REFERENCES forecast_runs(forecast_id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_forecast_runs_issue_time
            ON forecast_runs(issue_time_utc)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_forecast_predictions_target_time
            ON forecast_predictions(forecast_time_utc)
            """
        )

    print(
        "Forecast registry initialized successfully."
    )


# ============================================================
# MODEL VERSION IDENTIFICATION
# ============================================================

def get_model_version(method):
    """
    Use a SHA-256 checksum to identify the exact
    saved model artifact used for the forecast.

    Naive methods are identified by algorithm name.
    """

    if method in {
        "daily_naive",
        "weekly_naive",
    }:
        return f"{method}_v1"

    model_path = MODEL_FILES.get(method)

    if model_path is None:
        raise ValueError(
            f"Unsupported model method: {method}"
        )

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model artifact not found: {model_path}"
        )

    digest = hashlib.sha256()

    with model_path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return (
        f"{method}_sha256_"
        f"{digest.hexdigest()}"
    )


# ============================================================
# FORECAST VALIDATION
# ============================================================

def validate_forecast_dataframe(df):

    required_columns = [
        "issue_time_utc",
        "forecast_time_utc",
        "horizon",
        "requested_method",
        "selected_method",
        "step",
        "predicted_demand_mw",
    ]

    missing = (
        set(required_columns) - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"Missing forecast columns: {sorted(missing)}"
        )

    if df.empty:
        raise ValueError(
            "Cannot register an empty forecast."
        )

    issue_times = pd.to_datetime(
        df["issue_time_utc"],
        utc=True,
        errors="raise",
    )

    target_times = pd.to_datetime(
        df["forecast_time_utc"],
        utc=True,
        errors="raise",
    )

    if issue_times.isna().any():
        raise ValueError(
            "Forecast contains invalid issue timestamps."
        )

    if target_times.isna().any():
        raise ValueError(
            "Forecast contains invalid target timestamps."
        )

    for column in [
        "issue_time_utc",
        "horizon",
        "requested_method",
        "selected_method",
    ]:
        if df[column].nunique() != 1:
            raise ValueError(
                f"Forecast contains multiple {column} values."
            )

    horizon = df["horizon"].iloc[0]

    if horizon not in VALID_HORIZONS:
        raise ValueError(
            f"Unsupported forecast horizon: {horizon}"
        )

    expected_hours = VALID_HORIZONS[horizon]

    if len(df) != expected_hours:
        raise ValueError(
            "Forecast length does not match horizon."
        )

    selected_method = df[
        "selected_method"
    ].iloc[0]

    if selected_method not in VALID_METHODS:
        raise ValueError(
            "Unsupported selected forecasting method."
        )

    requested_method = df[
        "requested_method"
    ].iloc[0]

    if requested_method not in (
        VALID_METHODS | {"auto"}
    ):
        raise ValueError(
            "Unsupported requested forecasting method."
        )

    if (
        requested_method != "auto"
        and requested_method != selected_method
    ):
        raise ValueError(
            "Requested and selected methods disagree."
        )

    steps = pd.to_numeric(
        df["step"],
        errors="raise",
    ).to_numpy(dtype=float)

    if not np.array_equal(
        steps,
        np.arange(1, expected_hours + 1),
    ):
        raise ValueError(
            "Forecast steps must be consecutive "
            "integers beginning at 1."
        )

    expected_targets = (
        issue_times.iloc[0]
        + pd.to_timedelta(
            steps - 1,
            unit="h",
        )
    )

    if not (
        target_times.reset_index(drop=True)
        == pd.DatetimeIndex(expected_targets)
    ).all():
        raise ValueError(
            "Forecast target timestamps do not "
            "match the issue time and lead steps."
        )

    predictions = pd.to_numeric(
        df["predicted_demand_mw"],
        errors="raise",
    ).to_numpy(dtype=float)

    if not np.isfinite(predictions).all():
        raise ValueError(
            "Forecast contains invalid predictions."
        )

    if (predictions <= 0).any():
        raise ValueError(
            "Forecast demand must be positive."
        )

    return {
        "issue_time_utc": (
            issue_times.iloc[0].isoformat()
        ),
        "horizon": horizon,
        "requested_method": requested_method,
        "selected_method": selected_method,
        "prediction_count": expected_hours,
        "target_times": target_times,
        "steps": steps.astype(int),
        "predictions": predictions,
    }


# ============================================================
# SAVE FORECAST
# ============================================================

def register_forecast(df):
    """
    Register a complete forecast atomically.

    A forecast is stored as a new run even when
    its issue time and method match an earlier run.
    """

    validated = validate_forecast_dataframe(df)

    model_version = get_model_version(
        validated["selected_method"]
    )

    forecast_id = str(uuid.uuid4())

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO forecast_runs (
                forecast_id,
                created_at_utc,
                issue_time_utc,
                horizon,
                requested_method,
                selected_method,
                model_version,
                prediction_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                forecast_id,
                created_at,
                validated["issue_time_utc"],
                validated["horizon"],
                validated["requested_method"],
                validated["selected_method"],
                model_version,
                validated["prediction_count"],
            ),
        )

        prediction_rows = [
            (
                forecast_id,
                timestamp.isoformat(),
                int(step),
                float(prediction),
            )
            for timestamp, step, prediction in zip(
                validated["target_times"],
                validated["steps"],
                validated["predictions"],
            )
        ]

        connection.executemany(
            """
            INSERT INTO forecast_predictions (
                forecast_id,
                forecast_time_utc,
                step,
                predicted_demand_mw
            )
            VALUES (?, ?, ?, ?)
            """,
            prediction_rows,
        )

    return forecast_id


# ============================================================
# READ FORECAST
# ============================================================

def get_forecast(forecast_id):

    with get_connection() as connection:

        result = pd.read_sql_query(
            """
            SELECT
                r.forecast_id,
                r.created_at_utc,
                r.issue_time_utc,
                r.horizon,
                r.requested_method,
                r.selected_method,
                r.model_version,
                p.forecast_time_utc,
                p.step,
                p.predicted_demand_mw

            FROM forecast_runs AS r

            JOIN forecast_predictions AS p
                ON r.forecast_id = p.forecast_id

            WHERE r.forecast_id = ?

            ORDER BY p.step
            """,
            connection,
            params=(forecast_id,),
        )

    for column in [
        "created_at_utc",
        "issue_time_utc",
        "forecast_time_utc",
    ]:
        if column in result.columns:
            result[column] = pd.to_datetime(
                result[column],
                utc=True,
            )

    return result


# ============================================================
# LIST FORECAST RUNS
# ============================================================

def list_forecast_runs(limit=20):

    with get_connection() as connection:

        result = pd.read_sql_query(
            """
            SELECT *
            FROM forecast_runs
            ORDER BY created_at_utc DESC
            LIMIT ?
            """,
            connection,
            params=(int(limit),),
        )

    return result


# ============================================================
# REGISTRY SUMMARY
# ============================================================

def get_registry_summary():

    with get_connection() as connection:

        runs = connection.execute(
            """
            SELECT COUNT(*)
            FROM forecast_runs
            """
        ).fetchone()[0]

        predictions = connection.execute(
            """
            SELECT COUNT(*)
            FROM forecast_predictions
            """
        ).fetchone()[0]

    return {
        "forecast_runs": runs,
        "forecast_predictions": predictions,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\nINNEVA.E — Forecast Registry"
    )
    print("----------------------------")

    initialize_registry()

    summary = get_registry_summary()

    print("\nREGISTRY SUMMARY")
    print(
        f"Forecast runs: "
        f"{summary['forecast_runs']:,}"
    )

    print(
        f"Hourly predictions: "
        f"{summary['forecast_predictions']:,}"
    )

    print("\nFORECAST REGISTRY READY")


if __name__ == "__main__":
    main()
