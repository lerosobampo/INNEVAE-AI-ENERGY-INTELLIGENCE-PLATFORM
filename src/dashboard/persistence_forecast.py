
"""
INNEVA.E - PERSISTENCE FORECAST DASHBOARD
Module 16 - Checkpoint 16.3B

Integrates the existing demand forecasting tool
with Streamlit.

The forecasting algorithm is not duplicated here.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ML_DIRECTORY = PROJECT_ROOT / "src" / "ml"

if str(ML_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(ML_DIRECTORY))

from demand_forecasting_tool import forecast_next_hour


REQUIRED_RESULT_FIELDS = {
    "status",
    "model",
    "predicted_demand_mw",
    "latest_observation_utc",
    "forecast_timestamp_utc",
    "forecast_horizon_hours",
    "generated_at_utc",
    "data_freshness",
}


def generate_persistence_forecast():
    """
    Execute the existing forecasting tool and
    validate its structured response.
    """

    result = forecast_next_hour()

    if not isinstance(result, dict):
        raise TypeError(
            "Forecasting tool must return a dictionary."
        )

    missing = REQUIRED_RESULT_FIELDS - result.keys()

    if missing:
        raise ValueError(
            f"Missing forecast fields: {sorted(missing)}"
        )

    if result["status"] != "success":
        raise ValueError(
            f"Forecasting tool returned: {result['status']}"
        )

    if result["model"] != "previous_hour_persistence":
        raise ValueError(
            "Unexpected forecasting model."
        )

    if result["data_freshness"] != "historical_snapshot":
        raise ValueError(
            "Unexpected data freshness classification."
        )

    prediction = float(result["predicted_demand_mw"])

    if not 0 <= prediction < float("inf"):
        raise ValueError(
            "Invalid predicted demand value."
        )

    latest_timestamp = pd.Timestamp(
        result["latest_observation_utc"]
    )

    target_timestamp = pd.Timestamp(
        result["forecast_timestamp_utc"]
    )

    if latest_timestamp.tzinfo is None:
        raise ValueError(
            "Latest observation timestamp must include timezone."
        )

    if target_timestamp.tzinfo is None:
        raise ValueError(
            "Forecast target timestamp must include timezone."
        )

    horizon = int(result["forecast_horizon_hours"])

    if horizon != 1:
        raise ValueError(
            "Unexpected forecast horizon."
        )

    if target_timestamp - latest_timestamp != pd.Timedelta(
        hours=horizon
    ):
        raise ValueError(
            "Forecast target does not match the stated horizon."
        )

    return result


def render_persistence_forecast():
    """
    Display the existing model's next-hour prediction.
    """

    st.subheader(
        "Next-Hour Persistence Forecast"
    )

    st.info(
        "This forecast is generated from the latest "
        "available historical demand observation. "
        "It is not a live electricity demand forecast."
    )

    if "innevae_persistence_forecast" not in st.session_state:
        st.session_state["innevae_persistence_forecast"] = None

    if st.button(
        "Generate / Refresh Forecast",
        key="generate_persistence_forecast",
        type="primary",
    ):

        try:
            with st.spinner(
                "Running the existing forecasting model..."
            ):
                result = generate_persistence_forecast()

            st.session_state[
                "innevae_persistence_forecast"
            ] = result
            st.success(
                "Forecast generated successfully. "
                "Results are displayed below."
            )

        except Exception as error:
            st.session_state[
                "innevae_persistence_forecast"
            ] = None

            st.error(
                f"Forecast generation failed: {error}"
            )

    result = st.session_state[
        "innevae_persistence_forecast"
    ]

    if result is not None:
        st.caption(
            "Last successful forecast run: "
            f"{result['generated_at_utc']}"
        )

    if result is None:
        st.caption(
            "Select Generate / Refresh Forecast "
            "to execute the existing Python model."
        )
        return

    latest_timestamp = pd.Timestamp(
        result["latest_observation_utc"]
    ).tz_convert("UTC")

    target_timestamp = pd.Timestamp(
        result["forecast_timestamp_utc"]
    ).tz_convert("UTC")

    generated_timestamp = pd.Timestamp(
        result["generated_at_utc"]
    ).tz_convert("UTC")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Predicted Demand",
            f"{result['predicted_demand_mw']:,.2f} MW",
        )

    with col2:
        st.metric(
            "Forecast Horizon",
            f"{result['forecast_horizon_hours']} hour",
        )

    with col3:
        st.metric(
            "Model",
            "Persistence",
        )

    st.write(
        "**Latest historical observation:**",
        latest_timestamp.strftime(
            "%d %B %Y, %H:%M UTC"
        ),
    )

    st.write(
        "**Forecast target:**",
        target_timestamp.strftime(
            "%d %B %Y, %H:%M UTC"
        ),
    )

    st.write(
        "**Forecast generated:**",
        generated_timestamp.strftime(
            "%d %B %Y, %H:%M UTC"
        ),
    )

    st.caption(
        "The generation timestamp indicates when the "
        "Python function ran, not when the historical "
        "electricity measurement was collected."
    )

    with st.expander("Model Details"):

        st.write(
            "Model:",
            result["model"],
        )

        st.write(
            "Forecast method:",
            "Previous-hour persistence",
        )

        st.write(
            "Forecast units:",
            result.get("units", "MW"),
        )

        st.write(
            "Data freshness:",
            result["data_freshness"],
        )

        st.write(
            "Assumption:",
            result.get("assumption", "Not specified"),
        )

        st.json(result)

    st.warning(
        "This model predicts that demand in the next "
        "hour equals the latest observed hourly demand. "
        "It does not incorporate weather, prices, "
        "calendar effects, or other predictive variables."
    )
