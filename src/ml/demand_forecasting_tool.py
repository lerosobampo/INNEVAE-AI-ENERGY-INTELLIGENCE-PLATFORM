"""INNEVA.E — one-hour historical persistence forecasting tool.

Checkpoint 17.8D. Reads the canonical 37-column historical CSV via
src/forecasting/unified_data_loader.py; never queries the legacy SQLite view.
"""

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORECASTING_DIRECTORY = PROJECT_ROOT / "src" / "forecasting"
if str(FORECASTING_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(FORECASTING_DIRECTORY))

from unified_data_loader import load_energy_history


def forecast_next_hour(mode="development_90d"):
    """Predict the hour following the selected dataset's final observation.

    Uses previous-hour persistence, not the trained ML forecast engine.
    Both available modes retain the original 37-column CSV schema.
    """
    df = load_energy_history(mode=mode)
    if len(df) < 2:
        raise ValueError("At least two hourly observations are required.")

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    latest_timestamp = pd.Timestamp(latest["hour_start_utc"])
    previous_timestamp = pd.Timestamp(previous["hour_start_utc"])

    if latest_timestamp - previous_timestamp != pd.Timedelta(hours=1):
        raise ValueError("The last two observations are not consecutive hours.")

    recent_demand = pd.to_numeric(
        pd.Series([previous["actual_load_mw"], latest["actual_load_mw"]]),
        errors="coerce",
    )
    if recent_demand.isna().any():
        raise ValueError("Recent actual_load_mw observations contain missing values.")
    if (recent_demand < 0).any():
        raise ValueError("Recent actual_load_mw observations contain negative values.")

    forecast_timestamp = latest_timestamp + pd.Timedelta(hours=1)
    return {
        "tool": "forecast_next_hour",
        "model": "previous_hour_persistence",
        "forecast_horizon_hours": 1,
        "latest_observation_utc": latest_timestamp.isoformat(),
        "forecast_timestamp_utc": forecast_timestamp.isoformat(),
        "predicted_demand_mw": round(float(recent_demand.iloc[-1]), 2),
        "units": "MW",
        "status": "success",
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_freshness": "historical_snapshot",
        "dataset_mode": mode,
        "observation_count": int(len(df)),
        "source_variable": "actual_load_mw",
        "assumption": (
            "Historical persistence scenario: the last observed demand "
            "is carried forward by one hour. This is not a live forecast."
        ),
    }


if __name__ == "__main__":
    for selected_mode in ("development_90d", "full_history"):
        print(f"\n{selected_mode}")
        print(json.dumps(forecast_next_hour(mode=selected_mode), indent=2))
